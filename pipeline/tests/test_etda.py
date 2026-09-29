import json
from pathlib import Path

import httpx
import pytest
import respx

from aptx.core import http
from aptx.core.snapshot import SnapshotStore
from aptx.sources import etda
from aptx.sources.base import Connector
from aptx.sources.etda import EtdaConnector

FIX = Path(__file__).parent / "fixtures" / "etda_min.json"
AUDITED = "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License"


def save(tmp_path, payload: bytes = FIX.read_bytes()) -> SnapshotStore:
    s = SnapshotStore(tmp_path)
    s.save("etda", etda.FILE, payload)
    return s


def with_licence(licence) -> bytes:
    data = json.loads(FIX.read_bytes())
    if licence is None:
        del data["license"]
    else:
        data["license"] = licence
    return json.dumps(data).encode("utf-8")


@pytest.fixture
def store(tmp_path):
    return save(tmp_path)


@pytest.fixture
def sources_md(tmp_path):
    # The shared tests/fixtures/SOURCES.md sets etda to evidence-only for the
    # parser tests, so these tests write the value they need.
    p = tmp_path / "SOURCES.md"
    p.write_text("| Source | publish |\n|---|---|\n| ETDA Threat Group Cards (`etda`) | derived-only |\n",
                 encoding="utf-8")
    return p


def actors(store):
    return {a.name: a for a in EtdaConnector().normalize(store).actors}


def test_name_is_the_first_card_name_and_aliases_are_the_rest(store):
    # The card's "actor" field joins several names into one display string,
    # "APT 28, Fancy Bear, Sofacy", which no other source would ever match.
    a = actors(store)["APT 28"]
    assert (a.source, a.source_id) == ("etda", "00000000-0000-4000-8000-0000000e7da1")
    assert a.aliases == ["Fancy Bear", "Sofacy"]


def test_short_values_are_mapped(store):
    a = actors(store)["APT 28"]
    assert a.origin == ["Russia"]
    assert a.motivation == ["Information theft and espionage"]
    assert a.targets_countries == ["Georgia", "USA"]
    assert a.targets_sectors == ["Defense", "Government"]
    # ETDA gives a bare year. It is kept at that precision, because turning
    # it into a full date would claim a day and month ETDA never gave.
    assert a.first_seen == ["2004"]


def test_placeholders_and_unreadable_years_are_dropped(store):
    a = actors(store)["Clockwork Spider"]
    assert a.origin == []
    assert a.first_seen == []


def test_card_without_names_falls_back_to_the_actor_field(store):
    a = actors(store)["No Names Card"]
    assert a.aliases == ["Second Name"]
    assert a.origin == ["China"]


def test_card_without_any_name_is_dropped_and_logged(store, caplog):
    with caplog.at_level("WARNING"):
        names = set(actors(store))
    assert names == {"APT 28", "Clockwork Spider", "No Names Card"}
    assert "etda: dropped 1" in caplog.text


def test_free_text_never_reaches_a_record(store):
    # ETDA is derived-only: its description, information and operation
    # activity text may never be published. Every such field in the fixture
    # holds a SENTINEL marker, so one search covers every record field.
    b = EtdaConnector().normalize(store)
    assert b.actors
    assert "SENTINEL" not in b.model_dump_json()


def test_sponsor_prose_and_tool_lists_are_left_out(store):
    # ETDA's sponsor field is prose, often quoting a vendor, where the data
    # contract expects a state name. Its tool lists mix malware with phrases
    # such as "Living off the Land". Neither is taken.
    a = actors(store)["APT 28"]
    assert (a.sponsor, a.malware) == ([], [])


def test_policy_follows_sources_md_when_the_licence_is_the_audited_one(store, sources_md):
    assert EtdaConnector().policy(store, sources_md) == "derived-only"


@pytest.mark.parametrize("licence", [
    "Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 International License",
    "All rights reserved",
    "",
    None,
])
def test_licence_drift_makes_etda_evidence_only(tmp_path, sources_md, caplog, licence):
    # The audit read one licence string. Any other string, or none, means a
    # person must read the terms again before anything from ETDA is published.
    store = save(tmp_path, with_licence(licence))
    with caplog.at_level("WARNING"):
        assert EtdaConnector().policy(store, sources_md) == "evidence-only"
    assert "etda" in caplog.text and "licence" in caplog.text
    # The records still feed the resolver as evidence.
    assert EtdaConnector().normalize(store).actors


def test_licence_whitespace_is_not_drift(tmp_path, sources_md):
    store = save(tmp_path, with_licence("  " + AUDITED.replace(" 4.0 ", "  4.0\n") + " "))
    assert EtdaConnector().policy(store, sources_md) == "derived-only"


def test_policy_is_evidence_only_without_sources_md(store, tmp_path):
    assert EtdaConnector().policy(store, tmp_path / "missing" / "SOURCES.md") == "evidence-only"


def test_policy_is_evidence_only_without_a_snapshot(tmp_path, sources_md):
    assert EtdaConnector().policy(SnapshotStore(tmp_path / "empty"), sources_md) == "evidence-only"


def test_last_db_change_is_read_for_source_health(store, tmp_path):
    # ETDA's database has not changed since 2025-08-16. Source health shows
    # that date, because the fetch itself keeps succeeding.
    assert etda.last_db_change(store) == "2025-08-16"
    assert etda.last_db_change(SnapshotStore(tmp_path / "empty")) is None


def test_retrieved_at_is_the_snapshot_date(tmp_path):
    d = tmp_path / "etda" / "2026-01-02"
    d.mkdir(parents=True)
    (d / etda.FILE).write_bytes(FIX.read_bytes())
    b = EtdaConnector().normalize(SnapshotStore(tmp_path))
    assert {a.retrieved_at for a in b.actors} == {"2026-01-02"}


def test_no_snapshot_gives_an_empty_bundle(tmp_path, caplog):
    with caplog.at_level("WARNING"):
        b = EtdaConnector().normalize(SnapshotStore(tmp_path))
    assert (b.source, b.actors) == ("etda", [])
    assert "etda" in caplog.text


def test_is_a_connector():
    assert isinstance(EtdaConnector(), Connector)
    assert EtdaConnector.name == "etda"


@pytest.fixture
def fast_http(monkeypatch):
    monkeypatch.setattr(http, "MIN_INTERVAL", 0)
    monkeypatch.setattr(http, "BACKOFF_BASE", 0)


@respx.mock
def test_fetch_saves_the_cards(tmp_path, fast_http):
    respx.get(etda.URL).mock(return_value=httpx.Response(200, content=FIX.read_bytes()))
    store = SnapshotStore(tmp_path)
    EtdaConnector().fetch(store)
    assert store.latest("etda", etda.FILE) == FIX.read_bytes()


@respx.mock
def test_fetch_refuses_a_file_with_no_cards(tmp_path, fast_http):
    # On a first run there is no earlier snapshot for the size guard to
    # compare against, so an empty file must be refused on its content.
    respx.get(etda.URL).mock(return_value=httpx.Response(
        200, content=json.dumps({"license": AUDITED, "values": []}).encode()))
    store = SnapshotStore(tmp_path)
    with pytest.raises(ValueError):
        EtdaConnector().fetch(store)
    assert store.latest_date("etda") is None
