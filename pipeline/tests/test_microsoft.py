from pathlib import Path

import httpx
import pytest
import respx

from aptx.core import http
from aptx.core.snapshot import ShrunkSnapshotError, SnapshotStore
from aptx.sources import microsoft
from aptx.sources.base import Connector
from aptx.sources.microsoft import MicrosoftConnector

FIX = Path(__file__).parent / "fixtures" / "microsoft_min.json"


@pytest.fixture
def store(tmp_path):
    s = SnapshotStore(tmp_path)
    s.save("microsoft", "MicrosoftMapping.json", FIX.read_bytes())
    return s


def actors(store):
    return {a.name: a for a in MicrosoftConnector().normalize(store).actors}


def test_maps_name_other_names_and_origin(store):
    a = actors(store)["Fixture Blizzard"]
    assert (a.source, a.source_id) == ("microsoft", "Fixture Blizzard")
    # Other names are split on commas, with stray spaces closed up.
    assert a.aliases == ["APT28", "Fancy Bear", "Storm-0001"]
    assert a.origin == ["Russia"]
    assert (a.sponsor, a.motivation, a.targets_countries, a.targets_sectors) == ([], [], [], [])


def test_the_actors_own_name_is_not_repeated_as_an_alias(store):
    assert actors(store)["Fixture Typhoon"].aliases == ["Storm-0002"]


def test_actor_kind_labels_are_not_origins(store):
    by = actors(store)
    # "China, Financially motivated" holds a country and a label about the actor.
    assert by["Fixture Typhoon"].origin == ["China"]
    assert by["Fixture Tsunami"].origin == ["Israel"]
    assert by["Fixture Tempest"].origin == []
    assert by["Fixture Sandstorm"].origin == []
    assert by["Fixture Sleet"].origin == ["Türkiye"]


def test_a_row_without_a_name_or_a_repeated_name_is_dropped(store, caplog):
    with caplog.at_level("WARNING"):
        names = [a.name for a in MicrosoftConnector().normalize(store).actors]
    assert "Nameless" not in names
    assert names.count("Fixture Blizzard") == 1 and "fixture BLIZZARD" not in names
    assert "dropped 2 rows" in caplog.text


def test_retrieved_at_is_the_snapshot_date_not_today(tmp_path):
    d = tmp_path / "microsoft" / "2026-01-02"
    d.mkdir(parents=True)
    (d / "MicrosoftMapping.json").write_bytes(FIX.read_bytes())
    b = MicrosoftConnector().normalize(SnapshotStore(tmp_path))
    assert {a.retrieved_at for a in b.actors} == {"2026-01-02"}


def test_no_snapshot_gives_an_empty_bundle(tmp_path, caplog):
    with caplog.at_level("WARNING"):
        b = MicrosoftConnector().normalize(SnapshotStore(tmp_path))
    assert (b.source, b.actors) == ("microsoft", [])
    assert "microsoft" in caplog.text


def test_is_a_connector():
    assert isinstance(MicrosoftConnector(), Connector)
    assert MicrosoftConnector.name == "microsoft"


@pytest.fixture
def fast_http(monkeypatch):
    monkeypatch.setattr(http, "MIN_INTERVAL", 0)
    monkeypatch.setattr(http, "BACKOFF_BASE", 0)


@respx.mock
def test_fetch_saves_the_table(tmp_path, fast_http):
    respx.get(microsoft.URL).mock(return_value=httpx.Response(200, content=FIX.read_bytes()))
    store = SnapshotStore(tmp_path)
    MicrosoftConnector().fetch(store)
    assert store.latest("microsoft", "MicrosoftMapping.json") == FIX.read_bytes()


@respx.mock
@pytest.mark.parametrize("body", [b"[]", b"{}", b'[{"Origin/Threat": "China"}]', b'{"error": "maintenance"}'])
def test_fetch_refuses_a_table_with_no_actors(tmp_path, fast_http, body):
    respx.get(microsoft.URL).mock(return_value=httpx.Response(200, content=body))
    store = SnapshotStore(tmp_path)
    with pytest.raises(ValueError):
        MicrosoftConnector().fetch(store)
    assert store.latest_date("microsoft") is None


@respx.mock
def test_shrunken_table_keeps_the_old_snapshot(tmp_path, fast_http):
    old = tmp_path / "microsoft" / "2026-01-02"
    old.mkdir(parents=True)
    (old / "MicrosoftMapping.json").write_bytes(FIX.read_bytes() + b" " * 100_000)
    respx.get(microsoft.URL).mock(return_value=httpx.Response(200, content=FIX.read_bytes()))
    store = SnapshotStore(tmp_path)
    with pytest.raises(ShrunkSnapshotError):
        MicrosoftConnector().fetch(store)
    assert store.latest_date("microsoft") == "2026-01-02"
