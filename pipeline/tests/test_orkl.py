import json
from pathlib import Path

import httpx
import pytest
import respx

from aptx.core import http
from aptx.core.dates import resolve_report_date
from aptx.core.snapshot import SnapshotStore
from aptx.core.urls import norm_url
from aptx.resolve import titles
from aptx.sources import base, orkl
from aptx.sources.base import Connector
from aptx.sources.orkl import API, OrklConnector, actor_tags

FIX = Path(__file__).parent / "fixtures"
PAGE = json.loads((FIX / "orkl_page.json").read_text(encoding="utf-8"))
TALOS, KIMSUKY, CERTFR = PAGE["data"]
TALOS_URL = "https://blog.talosintelligence.com/the-closed-quorum-inside-the-first-reported-autonomous-ai-c2-implant/"
DERIVED_KEYS = {"id", "sha1", "title", "report_names", "authors", "created_at", "file_creation_date",
                "references", "sources", "threat_actors", "files", "cves", "techniques_raw"}


def _policy(tmp_path, monkeypatch, value):
    # publish_policy() reads SOURCES.md, so each test states ORKL's row itself
    # rather than depending on the repository's current decision.
    p = tmp_path / "SOURCES.md"
    p.write_text(f"| Source | publish |\n|---|---|\n| ORKL (`orkl`) | {value} |\n", encoding="utf-8")
    monkeypatch.setattr(base, "SOURCES_MD", p)


def _store(tmp_path, entries=(TALOS, KIMSUKY, CERTFR)):
    s = SnapshotStore(tmp_path / "cache")
    lines = [json.dumps(OrklConnector._derive(e)) for e in entries]
    s.save("orkl", "entries.jsonl", ("\n".join(lines) + "\n").encode("utf-8"))
    return s


def _by_id(bundle):
    return {r.source_id: r for r in bundle.reports}


@pytest.fixture
def link_only(tmp_path, monkeypatch):
    _policy(tmp_path, monkeypatch, "link-only")


# _derive: the snapshot line

def test_derive_keeps_ids_and_drops_the_report_text():
    d = OrklConnector._derive(TALOS)
    assert set(d) == DERIVED_KEYS
    assert "plain_text" not in d
    assert d["cves"] == ["CVE-2023-23397"]
    # Every well-formed ID is kept here; normalize() filters by ATT&CK.
    assert d["techniques_raw"] == ["T1059.001", "T9999"]
    assert d["sha1"] == "19f38ef695903486bbe533ed0b22733c8766f725"
    assert d["files"] == {"pdf": TALOS["files"]["pdf"], "text": TALOS["files"]["text"]}


def test_derive_keeps_actor_tags_as_evidence_only_fields():
    tags = OrklConnector._derive(KIMSUKY)["threat_actors"]
    # One tag per source that ORKL matched, with only the fields the resolver
    # needs; ORKL's own IDs, timestamps and tool lists are dropped.
    assert [t["source_name"] for t in tags] == ["MITRE:Kimsuky", "MISPGALAXY:Kimsuky", "ETDA:Kimsuky",
                                                "Secureworks:NICKEL KIMBALL"]
    assert tags[0] == {"main_name": "Kimsuky", "aliases": ["Kimsuky", "Black Banshee", "Velvet Chollima", "Emerald Sleet"],
                       "source_name": "MITRE:Kimsuky"}
    # Secureworks aliases arrive with trailing spaces.
    assert tags[3]["aliases"] == ["ARCHIPELAGO", "Black Banshee", "ITG16", "Kimsuky"]


def test_derive_tolerates_nulls_wherever_orkl_sends_them():
    # ORKL sends null for empty lists, at the top level and inside entries.
    entry = dict(CERTFR, references=None, sources=None, files=None, report_names=None, sha1_hash=None)
    d = OrklConnector._derive(entry)
    assert (d["threat_actors"], d["cves"], d["techniques_raw"]) == ([], [], [])
    assert (d["references"], d["sources"], d["files"], d["report_names"], d["sha1"]) == ([], [], {}, [], None)


def test_derive_refuses_an_entry_without_an_id():
    with pytest.raises(ValueError):
        OrklConnector._derive(dict(TALOS, id=None))


# normalize

def test_normalize_builds_link_only_report_records(tmp_path, link_only):
    s = _store(tmp_path)
    r = _by_id(OrklConnector().normalize(s))[TALOS["id"]]
    assert (r.source, r.url, r.archive_url) == ("orkl", TALOS_URL, TALOS["files"]["pdf"])
    assert r.sha1 == "19f38ef695903486bbe533ed0b22733c8766f725"
    assert r.title == "The Closed Quorum: Inside the first reported autonomous AI C2 implant"
    assert r.cves == ["CVE-2023-23397"]
    assert r.retrieved_at == s.latest_date("orkl")


def test_actor_tags_stay_out_of_reports_while_orkl_is_link_only(tmp_path, link_only):
    # ORKL's tags are matching evidence only until ORKL grants permission, so
    # no report record carries them.
    bundle = OrklConnector().normalize(_store(tmp_path))
    assert all(r.actor_names == [] for r in bundle.reports)


def test_actor_tags_appear_once_the_policy_allows_them(tmp_path, monkeypatch):
    _policy(tmp_path, monkeypatch, "derived-only")
    r = _by_id(OrklConnector().normalize(_store(tmp_path)))[KIMSUKY["id"]]
    # Three sources tag the report "Kimsuky"; the name appears once.
    assert r.actor_names == ["Kimsuky", "NICKEL KIMBALL"]


def test_actor_tags_accessor_exposes_the_evidence(tmp_path):
    assert actor_tags(_store(tmp_path)) == {KIMSUKY["id"]: OrklConnector._derive(KIMSUKY)["threat_actors"]}


def test_techniques_are_published_only_when_attack_defines_them(tmp_path, link_only):
    s = _store(tmp_path)
    assert _by_id(OrklConnector().normalize(s, valid_techniques={"T1059.001"}))[TALOS["id"]].techniques == ["T1059.001"]
    # With no ATT&CK set at all, nothing is published rather than everything.
    assert _by_id(OrklConnector().normalize(s))[TALOS["id"]].techniques == []


def test_the_malpedia_library_date_wins_when_it_matches(tmp_path, link_only):
    lib = {norm_url(TALOS_URL): "2026-09-20"}
    r = _by_id(OrklConnector().normalize(_store(tmp_path), lib_dates=lib))[TALOS["id"]]
    assert (r.published, r.date_basis) == ("2026-09-20", "malpedia-library")


def test_each_report_records_the_basis_of_its_date(tmp_path, link_only):
    reports = _by_id(OrklConnector().normalize(_store(tmp_path)))
    # No library match, and file_creation_date is 0001-01-01: the ingest date.
    assert (reports[TALOS["id"]].published, reports[TALOS["id"]].date_basis) == ("2026-09-29", "orkl-ingest")
    assert (reports[KIMSUKY["id"]].published, reports[KIMSUKY["id"]].date_basis) == ("2022-02-21", "file-metadata")
    assert (reports[CERTFR["id"]].published, reports[CERTFR["id"]].date_basis) == ("2023-11-15", "orkl-ingest")


def test_a_report_with_no_usable_date_is_undated_not_year_1(tmp_path, link_only):
    entry = dict(CERTFR, created_at="0001-01-01T00:00:00Z")
    r = OrklConnector().normalize(_store(tmp_path, [entry])).reports[0]
    assert (r.published, r.date_basis) == (None, "unknown")


# The resolver's cases for ORKL's own values (tests/test_report_date.py holds
# the general ones).

def test_orkl_timestamps_with_fractions_resolve_to_their_day():
    assert resolve_report_date([], {}, "0001-01-01T00:00:00Z", "2023-11-15T02:06:06.773743Z") == ("2023-11-15", "orkl-ingest")


def test_a_library_match_on_a_later_reference_still_counts():
    lib = {norm_url(TALOS_URL): "2026-09-20"}
    assert resolve_report_date(["https://example.com/mirror", TALOS_URL], lib, None, None) == ("2026-09-20", "malpedia-library")


def test_an_empty_title_falls_back_to_the_file_name_not_orkls_generated_title(tmp_path, link_only):
    r = _by_id(OrklConnector().normalize(_store(tmp_path)))[CERTFR["id"]]
    assert r.title == "CERTFR-2023-CTI-009.pdf"


def test_titles_are_single_trimmed_lines(tmp_path, link_only):
    entry = dict(TALOS, title="  Russian GRU Targeting\r\n Western   Logistics ")
    assert OrklConnector().normalize(_store(tmp_path, [entry])).reports[0].title == "Russian GRU Targeting Western Logistics"


def test_a_report_with_no_name_at_all_is_titled_by_its_url(tmp_path, link_only):
    entry = dict(TALOS, title="", report_names=None)
    assert OrklConnector().normalize(_store(tmp_path, [entry])).reports[0].title == TALOS_URL


def test_organisation_comes_from_the_authors_field(tmp_path, link_only):
    reports = _by_id(OrklConnector().normalize(_store(tmp_path)))
    assert (reports[KIMSUKY["id"]].organisation, reports[TALOS["id"]].organisation) == ("ESTSecurity", None)


def test_only_http_links_are_published(tmp_path, link_only):
    entry = dict(TALOS, references=["", "ftp://files.example.com/r.pdf", "https://example.com/r"],
                 files={"pdf": "archive.orkl.eu/x.pdf", "text": None})
    r = OrklConnector().normalize(_store(tmp_path, [entry])).reports[0]
    assert (r.url, r.archive_url) == ("https://example.com/r", None)


def test_a_reference_with_spaces_is_kept_as_an_encoded_link(tmp_path, link_only):
    # On the live library about a third of the entries are vx-underground
    # papers whose reference holds raw spaces and curly quotes. Dropping them
    # left 10,207 reports without their original link.
    entry = json.loads((FIX / "orkl_vxug_entry.json").read_text(encoding="utf-8"))
    r = OrklConnector().normalize(_store(tmp_path, [entry])).reports[0]
    assert r.url == ("https://papers.vx-underground.org/papers/Malware%20Defense/Malware%20Analysis%202023/"
                     "2023-05-17%20-%20Andariel%E2%80%99s%20%E2%80%9CJupiter%E2%80%9D%20malware%20and%20the"
                     "%20case%20of%20the%20curious%20C2.pdf")
    assert not any(c.isspace() for c in r.url)


def test_encoding_a_link_leaves_a_clean_one_and_existing_escapes_alone():
    assert orkl._http_url("https://example.com/a%20b?q=1&r=2#frag") == "https://example.com/a%20b?q=1&r=2#frag"
    assert orkl._http_url("  https://example.com/a b  ") == "https://example.com/a%20b"
    assert orkl._http_url("ftp://example.com/a b") is None


def test_malformed_snapshot_lines_are_dropped_and_counted(tmp_path, link_only, caplog):
    s = SnapshotStore(tmp_path / "cache")
    good = json.dumps(OrklConnector._derive(TALOS))
    s.save("orkl", "entries.jsonl", f"{good}\nnot json\n{{\"title\": \"no id\"}}\n\n".encode("utf-8"))
    with caplog.at_level("WARNING"):
        bundle = OrklConnector().normalize(s)
    assert [r.source_id for r in bundle.reports] == [TALOS["id"]]
    assert "dropped 2" in caplog.text


def test_no_snapshot_gives_an_empty_bundle(tmp_path, link_only):
    bundle = OrklConnector().normalize(SnapshotStore(tmp_path / "cache"))
    assert (bundle.source, bundle.reports) == ("orkl", [])


def test_is_a_connector():
    assert isinstance(OrklConnector(), Connector)
    assert OrklConnector.name == "orkl"


# fetch

@pytest.fixture
def fast_http(monkeypatch):
    # test_http changes these globals and never restores them, so every test
    # that makes requests sets both itself.
    monkeypatch.setattr(http, "MIN_INTERVAL", 0)
    monkeypatch.setattr(http, "BACKOFF_BASE", 0)
    monkeypatch.setattr(orkl, "PAGE_SIZE", 2)


def _mock(pages: dict, total: int):
    """Serve `pages` ({offset: entries or None}) and return the entries route."""
    respx.get(f"{API}/library/info").mock(return_value=httpx.Response(
        200, json={"status": "success", "data": {"library_entries": total}}))

    def page(request):
        p = request.url.params
        assert (p["order_by"], p["order"], p["limit"]) == ("created_at", "desc", "2")
        return httpx.Response(200, json={"status": "success", "data": pages.get(int(p["offset"]))})
    return respx.get(f"{API}/library/entries").mock(side_effect=page)


def _lines(store):
    return [json.loads(line) for line in store.latest("orkl", "entries.jsonl").decode("utf-8").splitlines()]


@respx.mock
def test_backfill_pages_until_a_short_page_and_never_stores_report_text(tmp_path, fast_http):
    route = _mock({0: [TALOS, KIMSUKY], 2: [CERTFR]}, total=3)
    s = SnapshotStore(tmp_path)
    OrklConnector().fetch(s)
    assert route.call_count == 2
    assert [e["id"] for e in _lines(s)] == [TALOS["id"], KIMSUKY["id"], CERTFR["id"]]
    raw = s.latest("orkl", "entries.jsonl")
    assert b"plain_text" not in raw and b"Synthetic fixture text" not in raw


@respx.mock
def test_a_null_data_page_ends_the_paging(tmp_path, fast_http):
    route = _mock({0: [TALOS, KIMSUKY], 2: None}, total=2)
    s = SnapshotStore(tmp_path)
    OrklConnector().fetch(s)
    assert route.call_count == 2
    assert len(_lines(s)) == 2


@respx.mock
def test_weekly_run_stops_at_the_first_known_entry_and_keeps_the_older_lines(tmp_path, fast_http):
    s = _store(tmp_path, [KIMSUKY, CERTFR])
    route = _mock({0: [TALOS, KIMSUKY], 2: [CERTFR]}, total=3)
    OrklConnector().fetch(s)
    assert route.call_count == 1
    assert [e["id"] for e in _lines(s)] == [TALOS["id"], KIMSUKY["id"], CERTFR["id"]]


@respx.mock
def test_a_quiet_week_still_counts_as_a_fetch(tmp_path, fast_http):
    # Nothing new: the first entry is already known, which proves ORKL answered.
    s = _store(tmp_path, [TALOS, KIMSUKY, CERTFR])
    route = _mock({0: [TALOS, KIMSUKY]}, total=3)
    OrklConnector().fetch(s)
    assert route.call_count == 1
    assert len(_lines(s)) == 3


@pytest.mark.parametrize("pages", [{0: None}, {0: [TALOS]}])
@respx.mock
def test_an_outage_never_resaves_the_old_snapshot_as_fresh(tmp_path, fast_http, pages):
    # An empty answer, or one that ends before any known entry, proves nothing
    # about the library. Re-saving the old lines under today's date would make
    # the source look fresh, so the run fails and the source is marked stale.
    s = _store(tmp_path, [KIMSUKY, CERTFR])
    before = s.latest("orkl", "entries.jsonl")
    _mock(pages, total=3)
    with pytest.raises(ValueError):
        OrklConnector().fetch(s)
    assert s.latest("orkl", "entries.jsonl") == before


@respx.mock
def test_a_server_that_ignores_the_offset_cannot_loop_forever(tmp_path, fast_http):
    route = _mock({i: [TALOS, KIMSUKY] for i in range(0, 20, 2)}, total=2)
    s = SnapshotStore(tmp_path)
    OrklConnector().fetch(s)
    assert route.call_count == 2
    assert len(_lines(s)) == 2


@respx.mock
def test_an_incomplete_backfill_is_not_saved(tmp_path, fast_http):
    # The weekly run trusts the snapshot to hold every older entry, so a
    # truncated first run saved here would leave a gap no later run fills.
    _mock({0: [TALOS, KIMSUKY], 2: [CERTFR]}, total=100)
    s = SnapshotStore(tmp_path)
    with pytest.raises(ValueError):
        OrklConnector().fetch(s)
    assert s.latest_date("orkl") is None


@respx.mock
def test_an_empty_library_saves_nothing(tmp_path, fast_http):
    _mock({0: None}, total=0)
    s = SnapshotStore(tmp_path)
    with pytest.raises(ValueError):
        OrklConnector().fetch(s)
    assert s.latest_date("orkl") is None


# Titles and dates from VX-Underground entries

def _vx(title, names, ref, **over):
    entry = dict(TALOS, title=title, report_names=names, references=[ref], sources=["VXUG"],
                 file_creation_date="2022-05-28T21:52:51Z", created_at="2023-01-12T15:06:43Z")
    entry.update(over)
    return entry


VX_BASE = "https://papers.vx-underground.org/papers/"


def test_a_filed_date_prefix_moves_from_the_title_to_the_date(tmp_path, link_only):
    e = _vx("2014-11-14 - OnionDuke- APT Attacks Via the Tor Network", None,
            VX_BASE + "Malware Defense/2014-11-14 - OnionDuke- APT Attacks Via the Tor Network.pdf")
    r = OrklConnector().normalize(_store(tmp_path, [e])).reports[0]
    assert r.title == "OnionDuke- APT Attacks Via the Tor Network"
    assert (r.published, r.date_basis) == ("2014-11-14", "title-date")


def test_a_title_that_belongs_to_another_document_is_replaced_by_the_file_name(tmp_path, link_only):
    # The live library has 177 papers whose title, link and file date point at different documents.
    # The file name agrees with the link and the archived copy, so it is the name to show, and the
    # wrong title's date prefix must not date the paper.
    name = "EPRI - ICCP Protocol - Threats to Data Security and Potential Solutions.pdf"
    e = _vx("2016-07-13 - Troldesh ransomware influenced by (the) Da Vinci code", [name],
            VX_BASE + "ICS SCADA/ICS Vulnerabilities/" + name, file_creation_date="2001-10-25T16:10:26Z")
    r = OrklConnector().normalize(_store(tmp_path, [e])).reports[0]
    assert r.title == name
    assert (r.published, r.date_basis) == ("2001-10-25", "file-metadata")


def test_a_title_that_matches_its_file_name_is_kept(tmp_path, link_only):
    e = _vx("2016-07-13 - Troldesh ransomware influenced by (the) Da Vinci code",
            ["2016-07-13 - Troldesh ransomware influenced by (the) Da Vinci code.pdf"],
            VX_BASE + "Malware Defense/Malware Analysis 2016/2016-07-13 - Troldesh ransomware influenced by (the) Da Vinci code.pdf")
    r = OrklConnector().normalize(_store(tmp_path, [e])).reports[0]
    assert r.title == "Troldesh ransomware influenced by (the) Da Vinci code"


def test_only_vx_underground_entries_are_checked_against_their_file_name(tmp_path, link_only):
    # A blog slug is often unlike the post's title, so the check would drop good titles elsewhere.
    e = dict(TALOS, title="Completely different words here", references=["https://example.com/zzz-qqq-xxx"],
             report_names=["zzz-qqq-xxx.pdf"], sources=["ORKL"])
    assert OrklConnector().normalize(_store(tmp_path, [e])).reports[0].title == "Completely different words here"


# Names in the text

def _names():
    aliases = {"G0007": ["APT28", "Fancy Bear"], "G0500": ["Storm-0558"]}

    def lookup(name):
        key = titles.norm(name)
        hits = {a for a, v in aliases.items() if any(titles.norm(x) == key for x in v)}
        return next(iter(hits)) if len(hits) == 1 else None
    return titles.build(aliases, lookup, lambda phrase: False)


def _with_text(entry, text):
    return {**entry, "plain_text": text}


def test_derive_keeps_the_names_found_in_the_text_and_never_the_text():
    text = "Intro sentence. Fancy Bear returned. Fancy Bear and APT28 again."
    d = OrklConnector._derive(_with_text(TALOS, text), _names())
    assert d["mentions"] == [{"name": "fancy bear", "count": 2, "first": 2}, {"name": "apt28", "count": 1, "first": 8}]
    assert "Intro sentence" not in json.dumps(d)
    assert "mentions" not in OrklConnector._derive(TALOS)


def test_a_read_text_with_no_names_still_records_that_it_was_read():
    assert OrklConnector._derive(_with_text(TALOS, "Nothing here."), _names())["mentions"] == []
    assert OrklConnector._derive(_with_text(TALOS, None), _names())["mentions"] == []


def test_normalize_carries_the_stored_mentions_and_drops_malformed_ones(tmp_path, link_only):
    line = OrklConnector._derive(_with_text(TALOS, "APT28 APT28"), _names())
    line["mentions"] += [{"name": "", "count": 1, "first": 0}, {"name": "x", "count": 0, "first": 0}, "junk",
                         {"name": "y", "count": 1, "first": -1}]
    s = SnapshotStore(tmp_path / "cache")
    s.save("orkl", "entries.jsonl", (json.dumps(line) + "\n").encode("utf-8"))
    report = _by_id(OrklConnector().normalize(s))[TALOS["id"]]
    assert [(m.name, m.count, m.first) for m in report.name_mentions] == [("apt28", 2, 0)]


@respx.mock
def test_a_matcher_reads_lines_saved_without_names_and_pages_to_the_end(tmp_path, fast_http):
    s = _store(tmp_path, [TALOS, KIMSUKY, CERTFR])
    route = _mock({0: [_with_text(TALOS, "APT28 APT28"), KIMSUKY], 2: [CERTFR]}, total=3)
    c = OrklConnector()
    c.matcher = _names()
    c.fetch(s)
    assert route.call_count == 2
    lines = _lines(s)
    assert all("mentions" in line for line in lines)
    assert lines[0]["mentions"] == [{"name": "apt28", "count": 2, "first": 0}]


@respx.mock
def test_once_every_line_is_read_a_weekly_run_stops_at_the_first_known_entry(tmp_path, fast_http):
    c = OrklConnector()
    c.matcher = _names()
    s = SnapshotStore(tmp_path)
    lines = [json.dumps(OrklConnector._derive(e, c.matcher)) for e in (KIMSUKY, CERTFR)]
    s.save("orkl", "entries.jsonl", ("\n".join(lines) + "\n").encode("utf-8"))
    route = _mock({0: [TALOS, KIMSUKY], 2: [CERTFR]}, total=3)
    c.fetch(s)
    assert route.call_count == 1
    assert [e["id"] for e in _lines(s)] == [TALOS["id"], KIMSUKY["id"], CERTFR["id"]]


@respx.mock
def test_unread_lines_do_not_excuse_a_truncated_answer(tmp_path, fast_http):
    s = _store(tmp_path, [KIMSUKY, CERTFR])
    before = s.latest("orkl", "entries.jsonl")
    _mock({i: [TALOS, KIMSUKY] for i in range(0, 20, 2)}, total=3)
    c = OrklConnector()
    c.matcher = _names()
    # The server repeats a page, so the run stops before the end of the library.
    with pytest.raises(ValueError):
        c.fetch(s)
    assert s.latest("orkl", "entries.jsonl") == before
