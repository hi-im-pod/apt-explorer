import json
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest
import respx

from aptx.core import http
from aptx.core.snapshot import SnapshotStore
from aptx.core.urls import norm_url as core_norm_url
from aptx.sources import malpedia
from aptx.sources.base import Connector
from aptx.sources.malpedia import (API, LIBRARY_URL, MalpediaConnector, actor_id, library_dates,
                                   norm_url, parse_bib, report_links)

FIX = Path(__file__).parent / "fixtures"
BULK_ACTORS = json.loads((FIX / "malpedia_actors.json").read_text(encoding="utf-8"))
FAMILIES = json.loads((FIX / "malpedia_family.json").read_text(encoding="utf-8"))
APT28_ITEM = json.loads((FIX / "malpedia_actor_apt28.json").read_text(encoding="utf-8"))
BIB = (FIX / "malpedia_min.bib").read_text(encoding="utf-8")
IDS = ["1937cn", "apt28"]


def _save(store, name, data):
    payload = data.encode("utf-8") if isinstance(data, str) else json.dumps(data).encode("utf-8")
    store.save("malpedia", name, payload)


@pytest.fixture
def store(tmp_path):
    """A snapshot as the bulk path saves it: actors keyed by Malpedia ID."""
    s = SnapshotStore(tmp_path)
    _save(s, "actors.json", {actor_id(a["value"]): a for a in BULK_ACTORS.values()})
    _save(s, "families.json", FAMILIES)
    _save(s, "library.bib", BIB)
    return s


def _by_id(records):
    return {r.source_id: r for r in records}


# normalize

def test_actor_normalizes_with_synonyms_values_and_family_names(store):
    bundle = MalpediaConnector().normalize(store)
    assert bundle.source == "malpedia"
    apt28 = _by_id(bundle.actors)["apt28"]
    assert apt28.name == "APT28"
    # Malpedia lists the display name among the synonyms; it is not an alias
    # of itself.
    assert apt28.aliases == ["Pawn Storm", "FANCY BEAR", "Sednit", "SNAKEMACKEREL", "Tsar Team", "TG-4127"]
    # Families are named by common_name, not by their IDs such as win.xagent.
    assert apt28.malware == ["Seduploader", "X-Agent"]
    assert apt28.origin == ["RU"]
    # The record's cfr-* fields cite a tracker whose terms bar public reuse,
    # so the connector never reads them, though the fixture carries them.
    assert apt28.sponsor == []
    assert apt28.motivation == []
    assert apt28.targets_countries == []
    assert apt28.targets_sectors == ["Military", "Government, Administration", "Security Service"]
    assert apt28.retrieved_at == store.latest_date("malpedia")


def test_actor_without_families_has_no_malware(store):
    cn = _by_id(MalpediaConnector().normalize(store).actors)["1937cn"]
    assert (cn.name, cn.malware, cn.origin, cn.aliases) == ("1937CN", [], ["CN"], [])


def test_families_become_malware_software_records(store):
    software = _by_id(MalpediaConnector().normalize(store).software)
    assert set(software) == {"win.xagent", "win.seduploader", "elf.wellmess", "win.7ev3n"}
    xagent = software["win.xagent"]
    assert (xagent.name, xagent.aliases, xagent.kind, xagent.source) == ("X-Agent", ["splm", "chopstick"], "malware", "malpedia")
    # An unattributed family is still a known malware name, which the resolver
    # needs to keep names such as 7ev3n from becoming actors.
    assert software["win.7ev3n"].kind == "malware"


def test_software_carries_the_family_attribution_names_verbatim(store):
    # "APT 29" is not any actor's display name, so the family is not in an
    # actor's malware list. The name is kept on the software record so the
    # resolver can still link the two.
    software = _by_id(MalpediaConnector().normalize(store).software)
    assert software["win.xagent"].attribution == ["APT28"]
    assert software["elf.wellmess"].attribution == ["APT 29"]
    assert software["win.7ev3n"].attribution == []


def test_attribution_names_are_trimmed_and_deduplicated(tmp_path):
    s = SnapshotStore(tmp_path)
    _save(s, "actors.json", {"apt28": {"value": "APT28", "meta": {}}})
    _save(s, "families.json", {"win.a": {"common_name": "A", "alt_names": [],
                                         "attribution": [" APT28 ", "APT28", "Sofacy\n"]}})
    [sw] = MalpediaConnector().normalize(s).software
    assert sw.attribution == ["APT28", "Sofacy"]


def test_family_without_a_common_name_is_named_from_its_id(tmp_path):
    # Six live families, such as win.idat_loader, have an empty common_name.
    # They are still malware the resolver must recognise, so they are kept.
    s = SnapshotStore(tmp_path)
    _save(s, "actors.json", {"apt28": dict(BULK_ACTORS["APT28"])})
    _save(s, "families.json", {"win.idat_loader": {"common_name": "", "alt_names": [], "attribution": ["APT28"]}})
    bundle = MalpediaConnector().normalize(s)
    assert [(r.source_id, r.name) for r in bundle.software] == [("win.idat_loader", "idat loader")]
    assert bundle.actors[0].malware == ["idat loader"]


def test_family_attributed_to_a_name_no_actor_uses_is_not_linked_by_guesswork(store):
    # elf.wellmess is attributed to "APT 29", which is not any actor's display
    # name. The connector does not guess a match; report_links keeps the name
    # verbatim for the resolver.
    bundle = MalpediaConnector().normalize(store)
    assert all("elf.wellmess" not in a.malware for a in bundle.actors)


def test_description_text_never_reaches_a_record(store):
    dumped = MalpediaConnector().normalize(store).model_dump_json()
    assert "Synthetic fixture text" not in dumped


def test_no_snapshot_gives_an_empty_bundle(tmp_path):
    bundle = MalpediaConnector().normalize(SnapshotStore(tmp_path))
    assert (bundle.source, bundle.actors, bundle.software) == ("malpedia", [], [])


def test_is_a_connector():
    assert isinstance(MalpediaConnector(), Connector)
    assert MalpediaConnector.name == "malpedia"


# IDs and URLs

@pytest.mark.parametrize("value, expected", [
    ("APT28", "apt28"),
    ("[Vault 7/8]", "[vault_7_8]"),
    ("Cyber fighters of Izz Ad-Din Al Qassam", "cyber_fighters_of_izz_ad-din_al_qassam"),
    ("TEMP.Veles", "temp.veles"),
])
def test_actor_id_follows_malpedias_own_rule(value, expected):
    assert actor_id(value) == expected


def test_norm_url_is_the_core_normalizer():
    # Both sides of the URL join must use one function, so this is a re-export.
    assert norm_url is core_norm_url


# the library

def test_library_dates_maps_a_normalized_url_to_its_date(store):
    dates = library_dates(store)
    assert dates[norm_url("http://example.com/a")] == "2021-05-06"
    assert dates[norm_url("https://welivesecurity.com/en/eset-research/sednit-reloaded-back-trenches")] == "2026-03-10"


def test_entry_without_a_date_is_skipped_and_urldate_is_not_a_date(store):
    # Entry b has only urldate, which is when Malpedia saw the page, not when
    # it was published.
    assert norm_url("https://example.com/b") not in library_dates(store)


def test_year_only_date_is_skipped(store):
    # A bare year would pin the report to 1 January and distort quarterly
    # trends, so the report falls through to its next date basis instead.
    assert norm_url("https://www.secureworks.com/research/threat-profiles/iron-twilight") not in library_dates(store)


def test_two_entries_for_one_url_keep_the_earliest_date(tmp_path):
    s = SnapshotStore(tmp_path)
    _save(s, "library.bib", "@online{b:1,\n   date = {2020-02-02},\n   url = {https://x.test/r}\n}\n\n"
                            "@online{a:1,\n   date = {2019-01-01},\n   url = {http://www.x.test/r/}\n}\n")
    assert library_dates(s) == {"x.test/r": "2019-01-01"}


def test_library_dates_without_a_snapshot_is_empty(tmp_path):
    assert library_dates(SnapshotStore(tmp_path)) == {}


def test_parse_bib_keeps_the_entry_key_and_strips_title_braces():
    entry = parse_bib(BIB)["research:20260310:sednit:86e9801"]
    assert entry["url"] == "https://www.welivesecurity.com/en/eset-research/sednit-reloaded-back-trenches/"
    assert entry["title"] == "Sednit reloaded: Back in the trenches"
    assert entry["date"] == "2026-03-10"


def test_parse_bib_tolerates_crlf_and_latex_escapes():
    text = "@online{k:1,\r\n   date = {2021-01-02},\r\n   url = {https://x.test/a\\_b}\r\n}\r\n"
    assert parse_bib(text)["k:1"] == {"date": "2021-01-02", "url": "https://x.test/a_b"}


def test_report_links_map_family_urls_and_library_entries_to_attribution_names(store):
    links = report_links(store)
    # A URL two APT28 families cite appears once.
    assert links[norm_url("https://securelist.com/a-slice-of-2017-sofacy-activity/83930/")] == ["APT28"]
    # A library entry resolves to its URL through the BibTeX key.
    assert links[norm_url("https://www.welivesecurity.com/en/eset-research/sednit-reloaded-back-trenches/")] == ["APT28"]
    # Attribution names are kept verbatim, even when no actor carries them.
    assert links[norm_url("https://blog.talosintelligence.com/2020/08/attribution-puzzle.html")] == ["APT 29"]
    # A family with no attribution links no report to anyone.
    assert norm_url("https://blog.malwarebytes.com/threat-analysis/2016/05/7ev3n-ransomware/") not in links


# fetch

@pytest.fixture
def fast_http(monkeypatch):
    # test_http changes these globals and never restores them, so every test
    # that makes requests sets both itself.
    monkeypatch.setattr(http, "MIN_INTERVAL", 0)
    monkeypatch.setattr(http, "BACKOFF_BASE", 0)


def _per_actor_bodies():
    cn = dict(BULK_ACTORS["1937CN"], families={})
    return {"apt28": APT28_ITEM, "1937cn": cn}


def _mock(ids=IDS, actors=BULK_ACTORS, families=FAMILIES, bib=BIB, per_actor=None):
    """Mock every Malpedia endpoint and return the per-actor route."""
    per_actor = _per_actor_bodies() if per_actor is None else per_actor
    respx.get(f"{API}/list/actors").mock(return_value=httpx.Response(200, json=ids))
    for path, body in (("get/actors", actors), ("get/families", families)):
        if isinstance(body, httpx.Response):
            respx.get(f"{API}/{path}").mock(return_value=body)
        else:
            respx.get(f"{API}/{path}").mock(return_value=httpx.Response(200, json=body))
    respx.get(LIBRARY_URL).mock(return_value=httpx.Response(200, text=bib))

    def one_actor(request):
        key = unquote(request.url.raw_path.decode("ascii").rsplit("/", 1)[1])
        return httpx.Response(200, json=per_actor[key]) if key in per_actor else httpx.Response(404)
    return respx.get(url__startswith=f"{API}/get/actor/").mock(side_effect=one_actor)


def _snapshot(store, name):
    return json.loads(store.latest("malpedia", name))


@respx.mock
def test_fetch_uses_the_bulk_endpoints_when_their_shape_holds(tmp_path, fast_http):
    per_actor = _mock()
    s = SnapshotStore(tmp_path)
    MalpediaConnector().fetch(s)
    assert per_actor.call_count == 0
    assert set(_snapshot(s, "actors.json")) == {"1937cn", "apt28"}
    assert set(_snapshot(s, "families.json")) == set(FAMILIES)
    assert s.latest("malpedia", "library.bib").decode("utf-8") == BIB
    assert _by_id(MalpediaConnector().normalize(s).actors)["apt28"].malware == ["Seduploader", "X-Agent"]


@pytest.mark.parametrize("bad_actors", [
    list(BULK_ACTORS.values()),          # a list instead of a dict keyed by name
    {},                                  # an empty payload
    httpx.Response(404),                 # the endpoint is gone
])
@respx.mock
def test_fetch_falls_back_to_one_call_per_actor(tmp_path, fast_http, bad_actors):
    per_actor = _mock(actors=bad_actors)
    s = SnapshotStore(tmp_path)
    MalpediaConnector().fetch(s)
    assert per_actor.call_count == 2
    actors = _snapshot(s, "actors.json")
    # Family bodies move to families.json, so actors.json has one shape in both
    # modes and a later bulk run never looks like a shrunken payload.
    assert actors["apt28"]["families"] == ["win.seduploader", "win.xagent"]
    assert set(_snapshot(s, "families.json")) == {"win.seduploader", "win.xagent"}
    assert _by_id(MalpediaConnector().normalize(s).actors)["apt28"].malware == ["Seduploader", "X-Agent"]


@respx.mock
def test_bulk_families_without_a_common_name_stay_in_the_snapshot(tmp_path, fast_http):
    _mock(families={**FAMILIES, "win.beep": {"common_name": "", "alt_names": [], "attribution": []}})
    s = SnapshotStore(tmp_path)
    MalpediaConnector().fetch(s)
    assert "win.beep" in _snapshot(s, "families.json")


@respx.mock
def test_fetch_falls_back_when_the_families_payload_is_unusable(tmp_path, fast_http):
    per_actor = _mock(families=["win.xagent"])
    MalpediaConnector().fetch(SnapshotStore(tmp_path))
    assert per_actor.call_count == 2


@respx.mock
def test_fallback_keeps_families_it_did_not_refetch(tmp_path, fast_http, store):
    # Per-actor calls return only attributed families, a fraction of the bulk
    # list. The rest carry over from the last snapshot, so entity typing keeps
    # them and the smaller payload does not trip the shrink guard.
    _mock(actors=httpx.Response(404))
    MalpediaConnector().fetch(store)
    assert set(_snapshot(store, "families.json")) == set(FAMILIES)


@respx.mock
def test_actor_missing_from_the_bulk_payload_is_fetched_alone(tmp_path, fast_http):
    newcomer = {"value": "New Group", "meta": {"country": "IR"}, "uuid": "x", "families": {}}
    per_actor = _mock(ids=IDS + ["new_group"], per_actor={"new_group": newcomer})
    s = SnapshotStore(tmp_path)
    MalpediaConnector().fetch(s)
    assert per_actor.call_count == 1
    assert set(_snapshot(s, "actors.json")) == {"1937cn", "apt28", "new_group"}


@respx.mock
def test_a_failed_gap_fill_call_skips_that_actor_only(tmp_path, fast_http, monkeypatch):
    # One listed actor Malpedia cannot serve must not push the whole run onto
    # a thousand per-actor calls that would hit the same error. One of three
    # is over the real 5% budget, so the test widens it.
    monkeypatch.setattr(malpedia, "MAX_FAILED_SHARE", 0.5)
    per_actor = _mock(ids=IDS + ["ghost"], per_actor={})
    s = SnapshotStore(tmp_path)
    MalpediaConnector().fetch(s)
    assert per_actor.call_count == 1
    assert set(_snapshot(s, "actors.json")) == {"1937cn", "apt28"}


@respx.mock
def test_fallback_skips_a_few_failed_actors(tmp_path, fast_http, monkeypatch):
    monkeypatch.setattr(malpedia, "MAX_FAILED_SHARE", 0.5)
    _mock(ids=IDS + ["ghost"], actors=httpx.Response(404))
    s = SnapshotStore(tmp_path)
    MalpediaConnector().fetch(s)
    assert set(_snapshot(s, "actors.json")) == {"1937cn", "apt28"}


@respx.mock
def test_fallback_fails_when_too_many_actors_fail(tmp_path, fast_http):
    # Most of the list failing means Malpedia is down, not that a few actors
    # are broken, so the last good snapshot stays.
    _mock(ids=IDS + ["ghost"], actors=httpx.Response(404), per_actor={"apt28": APT28_ITEM})
    s = SnapshotStore(tmp_path)
    with pytest.raises(ValueError):
        MalpediaConnector().fetch(s)
    assert s.latest_date("malpedia") is None


@respx.mock
def test_per_actor_ids_are_escaped_in_the_path(tmp_path, fast_http):
    vault = {"value": "[Vault 7/8]", "meta": {}, "uuid": "v", "families": {}}
    per_actor = _mock(ids=["[vault_7_8]"], actors=httpx.Response(404), per_actor={"[vault_7_8]": vault})
    MalpediaConnector().fetch(SnapshotStore(tmp_path))
    assert per_actor.calls[0].request.url.raw_path.endswith(b"/get/actor/%5Bvault_7_8%5D")


@pytest.mark.parametrize("ids, bib", [([], BIB), (IDS, ""), (IDS, "<html>maintenance</html>")])
@respx.mock
def test_empty_payloads_save_nothing(tmp_path, fast_http, ids, bib):
    _mock(ids=ids, bib=bib)
    s = SnapshotStore(tmp_path)
    with pytest.raises(ValueError):
        MalpediaConnector().fetch(s)
    assert s.latest_date("malpedia") is None


def test_a_family_many_actors_share_links_its_reports_to_none_of_them(tmp_path):
    from aptx.sources.malpedia import MAX_FAMILY_ACTORS
    s = SnapshotStore(tmp_path)
    shared = [f"Crew {n}" for n in range(MAX_FAMILY_ACTORS + 1)]
    _save(s, "families.json", {
        "win.plugx": {"common_name": "PlugX", "attribution": shared, "urls": ["https://ex.org/plugx-campaign"]},
        "win.small": {"common_name": "Small", "attribution": shared[:MAX_FAMILY_ACTORS],
                      "urls": ["https://ex.org/small"]}})
    _save(s, "library.bib", "")
    links = report_links(s)
    assert norm_url("https://ex.org/plugx-campaign") not in links
    assert links[norm_url("https://ex.org/small")] == sorted(shared[:MAX_FAMILY_ACTORS])
