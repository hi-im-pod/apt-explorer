"""The paper's Zenodo dataset (16869733) as an attributed historical layer.

paper_min.csv holds seven real rows of Information_Retrieved_Collection.csv,
downloaded on 2026-09-29, with only the YARA column blanked to keep the file
small. They were picked for the shapes the real data has: an empty Title, a
Filename with spaces, an actor name with a leading space, CVE IDs with
Unicode hyphens or truncated digits, and MITRE_ID codes that are software or
tactics rather than techniques. paper_actors_min.csv holds five real rows of
Threat_Actor_Collection.csv. Cases the real data lacks, such as "Not
mentioned" and a missing Date, are built inline.
"""
import csv
import io
import re
from pathlib import Path

import httpx
import pytest
import respx

from aptx.core import http
from aptx.core.snapshot import SnapshotStore
from aptx.sources.base import Connector
from aptx.sources.paper import (ACTORS_SNAPSHOT, ACTORS_URL, REPORTS_SNAPSHOT, REPORTS_URL, PaperConnector,
                                report_actor_names, unresolved_actor_names)

FIX = Path(__file__).parent / "fixtures"
REPORTS = (FIX / "paper_min.csv").read_bytes()
ACTORS = (FIX / "paper_actors_min.csv").read_bytes()
COLUMNS = ["Date", "Filename", "Title", "Download_url", "Source", "CVE", "MITRE_ID", "YARA", "Threat_actor",
           "Threat_country", "Motivation", "First_seen", "Victim_country", "Zero-day", "Attack_vector", "Malware",
           "Target_sector", "Attack_start_date", "Attack_end_date", "Attack_duration"]
REPORT_ID = re.compile(r"^[a-z][a-z0-9-]*:\S+$")
LABEL = re.compile(r"^\S(.*\S)?$")
CVE = re.compile(r"^CVE-[0-9]{4}-[0-9]{4,7}$")
TECHNIQUE = re.compile(r"^T[0-9]{4}(\.[0-9]{3})?$")
URL = re.compile(r"^https?://\S+$")


def csv_bytes(*rows: dict) -> bytes:
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=COLUMNS)
    w.writeheader()
    for row in rows:
        w.writerow({c: row.get(c, "") for c in COLUMNS})
    return out.getvalue().encode("utf-8")


def row(filename="report-a", **fields) -> dict:
    return {"Date": "2020-01-02", "Filename": filename, "Download_url": "https://example.org/a.pdf",
            "Source": "Example Lab", **fields}


def store_with(tmp_path, reports: bytes = REPORTS, actors: bytes | None = ACTORS) -> SnapshotStore:
    s = SnapshotStore(tmp_path)
    s.save("paper", REPORTS_SNAPSHOT, reports)
    if actors is not None:
        s.save("paper", ACTORS_SNAPSHOT, actors)
    return s


def by_title(bundle):
    return {r.title: r for r in bundle.reports}


@pytest.fixture
def store(tmp_path):
    return store_with(tmp_path)


@pytest.fixture
def no_wait(monkeypatch):
    # test_http changes these module globals and never restores them, so every
    # test that goes through the client sets them itself.
    monkeypatch.setattr(http, "MIN_INTERVAL", 0)
    monkeypatch.setattr(http, "BACKOFF_BASE", 0)


def test_is_a_connector_named_paper():
    assert PaperConnector.name == "paper"
    assert isinstance(PaperConnector(), Connector)


def test_each_row_becomes_a_dated_report(store):
    b = PaperConnector().normalize(store)
    assert b.source == "paper" and len(b.reports) == 7
    assert b.actors == [] and b.campaigns == [] and b.vulns == [] and b.software == []
    r = by_title(b)["Bears in the Midst: Intrusion into the Democratic National Committee"]
    assert r.source == "paper"
    assert r.source_id == "CrowdStrike_BearsintheMidst_DNC(06-04-2016)"
    assert (r.published, r.date_basis) == ("2016-06-04", "paper")
    assert r.organisation == "CrowdStrike"
    # Download_url becomes url, as the plan says, although most of these are
    # mirror copies rather than the publisher's own page.
    assert r.url == "https://app.box.com/s/x5sz7dw4as54b1rif3mdtqwzzj2aek68"
    assert r.archive_url is None and r.sha1 is None
    assert r.retrieved_at == store.latest_date("paper")


def test_an_empty_title_falls_back_to_the_filename(store):
    # 1,269 of the 1,509 real rows have no Title. The Filename is the only
    # name such a row has.
    titles = set(by_title(PaperConnector().normalize(store)))
    assert "Project_CAMERASHY_ThreatConnect_Copyright_2015" in titles
    assert "securelist.com-The Icefog APT Hits US Targets With Java Backdoor" in titles


def test_source_ids_have_no_whitespace_and_stay_distinct(tmp_path):
    # Two real rows differ only in doubled spaces in their Filename, so
    # collapsing whitespace would merge them. Percent-encoding keeps them
    # apart and keeps each ID traceable to its row.
    s = store_with(tmp_path, csv_bytes(
        row("Social Engineering  Remains Key Tradecraft  for Iranian APTs"),
        row("Social Engineering Remains Key Tradecraft for Iranian APTs")))
    ids = [r.source_id for r in PaperConnector().normalize(s).reports]
    assert ids == ["Social%20Engineering%20%20Remains%20Key%20Tradecraft%20%20for%20Iranian%20APTs",
                   "Social%20Engineering%20Remains%20Key%20Tradecraft%20for%20Iranian%20APTs"]
    b = PaperConnector().normalize(store_with(tmp_path / "real"))
    assert all(REPORT_ID.fullmatch(f"paper:{r.source_id}") for r in b.reports)


def test_cves_are_split_repaired_and_validated(store):
    r = by_title(PaperConnector().normalize(store))
    # U+2011 and U+2013 stand in for hyphens in the real data.
    assert r["WinorDLL64: A backdoor from the vast Lazarus arsenal?"].cves == ["CVE-2021-21551"]
    assert r["China Chopper still active 9 years later"].cves == [
        "CVE-2015-0062", "CVE-2015-1701", "CVE-2016-0099", "CVE-2018-8440"]
    # CVE-2012-015 has too few digits to name any CVE, so it is dropped.
    assert r["Project_CAMERASHY_ThreatConnect_Copyright_2015"].cves == ["CVE-2012-0158"]


def test_only_attack_technique_ids_are_kept(store):
    r = by_title(PaperConnector().normalize(store))
    # T9000 and T5000 are backdoor names, not techniques.
    assert r["T9000: Advanced Modular Backdoor Uses Complex Anti Analysis Techniques"].techniques == []
    # Tactic IDs such as TA0001 are dropped; the name after the colon is not kept.
    alert = next(v for k, v in r.items() if k.startswith("Alert (AA21-321A)"))
    assert alert.techniques == ["T1053", "T1136", "T1190", "T1486", "T1560", "T1588"]
    assert len(r["WinorDLL64: A backdoor from the vast Lazarus arsenal?"].techniques) == 18


def test_actor_names_are_split_and_trimmed(store):
    r = by_title(PaperConnector().normalize(store))
    assert r["Bears in the Midst: Intrusion into the Democratic National Committee"].actor_names == ["apt29", "apt28"]
    assert r["WinorDLL64: A backdoor from the vast Lazarus arsenal?"].actor_names == ["lazarus group"]
    assert next(v for k, v in r.items() if k.startswith("Alert (AA21-321A)")).actor_names == []


def test_not_mentioned_values_are_dropped(tmp_path):
    s = store_with(tmp_path, csv_bytes(row(
        Source="Not mentioned", CVE="Not mentioned, CVE-2020-0688", MITRE_ID="not mentioned",
        Threat_actor="Not Mentioned, apt10 ,  apt10")))
    [r] = PaperConnector().normalize(s).reports
    assert r.organisation is None
    assert r.cves == ["CVE-2020-0688"] and r.techniques == []
    assert r.actor_names == ["apt10"]


@pytest.mark.parametrize("value", ["", "  ", "Not mentioned", "0001-01-01", "1970-01-01", "2019-02-30", "soon"])
def test_a_row_without_a_usable_date_is_undated(tmp_path, value):
    # The contract ties a null date to the "unknown" basis, so such a row
    # goes to reports/undated.json instead of a year shard.
    s = store_with(tmp_path, csv_bytes(row(Date=value)))
    [r] = PaperConnector().normalize(s).reports
    assert (r.published, r.date_basis) == (None, "unknown")


def test_labels_are_single_trimmed_lines_and_bad_urls_become_none(tmp_path):
    s = store_with(tmp_path, csv_bytes(row(Title=" Two\n lines ", Source=" Lab\tName ", Download_url="report.pdf")))
    [r] = PaperConnector().normalize(s).reports
    assert (r.title, r.organisation, r.url) == ("Two lines", "Lab Name", None)


def test_rows_without_a_filename_or_a_repeated_one_are_dropped_and_counted(tmp_path, caplog):
    s = store_with(tmp_path, csv_bytes(row("same", Title="First"), row("same", Title="Second"),
                                       row("", Title="No filename")))
    with caplog.at_level("WARNING"):
        reports = PaperConnector().normalize(s).reports
    assert [r.title for r in reports] == ["First"]
    assert "paper: dropped 2 rows" in caplog.text


def test_records_meet_the_contract(store):
    for r in PaperConnector().normalize(store).reports:
        assert LABEL.fullmatch(r.title) and (r.organisation is None or LABEL.fullmatch(r.organisation))
        assert r.url is None or URL.fullmatch(r.url)
        assert all(CVE.fullmatch(c) for c in r.cves) and len(set(r.cves)) == len(r.cves)
        assert all(TECHNIQUE.fullmatch(t) for t in r.techniques) and len(set(r.techniques)) == len(r.techniques)
        assert all(LABEL.fullmatch(n) for n in r.actor_names) and len(set(r.actor_names)) == len(r.actor_names)
        assert (r.published is None) == (r.date_basis == "unknown")


def test_report_actor_names_are_the_distinct_names_across_rows(store):
    # The full real file gives 443 names, the denominator of the registry's
    # match rate in resolution.json.
    assert report_actor_names(store) == [
        "apt28", "apt29", "china chopper", "grand theft auto panda", "icefog", "lazarus group", "naikon"]


def test_unresolved_names_are_those_missing_from_the_papers_actor_list(store):
    # A name resolves when it equals, ignoring case, an actor's primary name or
    # one of its Other Names. "icefog" resolves through DAGGER PANDA's Other
    # Names. Against the full real files this rule gives the paper's 130.
    assert unresolved_actor_names(store) == ["china chopper", "grand theft auto panda"]


def test_without_snapshots_there_is_nothing(tmp_path):
    s = SnapshotStore(tmp_path)
    assert PaperConnector().normalize(s).reports == []
    assert report_actor_names(s) == []
    with pytest.raises(LookupError):
        unresolved_actor_names(s)
    with pytest.raises(LookupError):
        unresolved_actor_names(store_with(tmp_path / "reports-only", actors=None))


@respx.mock
def test_fetch_saves_both_files(tmp_path, no_wait):
    respx.get(REPORTS_URL).mock(return_value=httpx.Response(200, content=REPORTS))
    respx.get(ACTORS_URL).mock(return_value=httpx.Response(200, content=ACTORS))
    s = SnapshotStore(tmp_path)
    PaperConnector().fetch(s)
    assert s.latest("paper", REPORTS_SNAPSHOT) == REPORTS
    assert s.latest("paper", ACTORS_SNAPSHOT) == ACTORS


BROKEN = [b"", b"<html><body>Service unavailable</body></html>", b"Date,Filename\n2020-01-01,x\n"]


@respx.mock
@pytest.mark.parametrize("which", ["reports", "actors"])
@pytest.mark.parametrize("body", BROKEN + [csv_bytes()], ids=["empty", "html", "columns", "header-only"])
def test_fetch_refuses_a_broken_file_and_saves_neither(tmp_path, no_wait, which, body):
    # A 200 carrying an error page or a truncated file would otherwise become
    # the newest snapshot. Both files are checked before either is saved, so
    # the pair on disk always comes from one fetch.
    if which == "actors" and body == csv_bytes():
        body = b"Threat Actor,Other Names,Country,Sponsor,Motivation,First seen\n"
    respx.get(REPORTS_URL).mock(return_value=httpx.Response(200, content=body if which == "reports" else REPORTS))
    respx.get(ACTORS_URL).mock(return_value=httpx.Response(200, content=body if which == "actors" else ACTORS))
    s = SnapshotStore(tmp_path)
    with pytest.raises(ValueError):
        PaperConnector().fetch(s)
    assert s.latest_date("paper") is None
