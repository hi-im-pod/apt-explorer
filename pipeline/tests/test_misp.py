import json
from pathlib import Path

import httpx
import pytest
import respx

from aptx.core import http
from aptx.core.snapshot import SnapshotStore
from aptx.sources import misp
from aptx.sources.base import Connector
from aptx.sources.misp import MispConnector

FIX = Path(__file__).parent / "fixtures" / "misp_min.json"


@pytest.fixture
def store(tmp_path):
    s = SnapshotStore(tmp_path)
    s.save("misp", "threat-actor.json", FIX.read_bytes())
    return s


def actors(store):
    return {a.name: a for a in MispConnector().normalize(store).actors}


def test_maps_the_galaxy_fields(store):
    a = actors(store)["APT28"]
    assert a.source == "misp"
    assert a.source_id == "5b4ee3ea-eee3-4c8e-8323-85ae32658754"
    # Synonyms keep the galaxy's order, lose repeats and whitespace, and leave
    # out the actor's own name.
    assert a.aliases == ["Fancy Bear", "Sofacy", "G0007"]
    assert a.origin == ["RU"]
    assert a.sponsor == ["Russian Federation"]
    assert a.targets_countries == ["Georgia", "United States"]
    # Sectors come from both the CFR category and MISP's own sector field.
    assert a.targets_sectors == ["Government", "Military", "Defense"]
    assert a.motivation == ["Espionage"]


def test_bare_actor_still_normalizes_with_empty_lists(store):
    a = actors(store)["Bare Actor"]
    # Without a uuid, the name is the only stable handle the galaxy gives.
    assert a.source_id == "Bare Actor"
    assert (a.aliases, a.origin, a.sponsor, a.motivation, a.targets_countries, a.targets_sectors) == (
        [], [], [], [], [], [])


def test_scalar_meta_values_are_wrapped_and_unknown_is_dropped(store):
    a = actors(store)["Scalar Actor"]
    assert a.aliases == ["Scalar Synonym"]
    assert a.origin == ["IR"]
    assert a.targets_sectors == ["Civil society"]
    assert a.motivation == ["Hacktivists-Nationalists"]
    # "Unknown" says the galaxy has no sponsor to name; it is not a sponsor.
    assert a.sponsor == []


def test_record_without_a_name_is_dropped_and_logged(store, caplog):
    with caplog.at_level("WARNING"):
        names = set(actors(store))
    assert names == {"APT28", "Bare Actor", "Scalar Actor"}
    assert "misp: dropped 1" in caplog.text


def test_retrieved_at_is_the_snapshot_date(tmp_path):
    d = tmp_path / "misp" / "2026-01-02"
    d.mkdir(parents=True)
    (d / "threat-actor.json").write_bytes(FIX.read_bytes())
    b = MispConnector().normalize(SnapshotStore(tmp_path))
    assert {a.retrieved_at for a in b.actors} == {"2026-01-02"}


def test_no_snapshot_gives_an_empty_bundle(tmp_path, caplog):
    with caplog.at_level("WARNING"):
        b = MispConnector().normalize(SnapshotStore(tmp_path))
    assert (b.source, b.actors) == ("misp", [])
    assert "misp" in caplog.text


def test_is_a_connector():
    assert isinstance(MispConnector(), Connector)
    assert MispConnector.name == "misp"


@pytest.fixture
def fast_http(monkeypatch):
    monkeypatch.setattr(http, "MIN_INTERVAL", 0)
    monkeypatch.setattr(http, "BACKOFF_BASE", 0)


@respx.mock
def test_fetch_saves_the_cluster(tmp_path, fast_http):
    respx.get(misp.URL).mock(return_value=httpx.Response(200, content=FIX.read_bytes()))
    store = SnapshotStore(tmp_path)
    MispConnector().fetch(store)
    assert store.latest("misp", "threat-actor.json") == FIX.read_bytes()


@respx.mock
def test_fetch_refuses_a_cluster_with_no_values(tmp_path, fast_http):
    # On a first run there is no earlier snapshot for the size guard to
    # compare against, so an empty cluster must be refused on its content.
    respx.get(misp.URL).mock(return_value=httpx.Response(
        200, content=json.dumps({"name": "Threat Actor", "values": []}).encode()))
    store = SnapshotStore(tmp_path)
    with pytest.raises(ValueError):
        MispConnector().fetch(store)
    assert store.latest_date("misp") is None
