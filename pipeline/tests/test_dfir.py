import json
import re
from pathlib import Path

import httpx
import pytest
import respx

from aptx.core import http
from aptx.core.snapshot import SnapshotStore
from aptx.sources.base import Connector
from aptx.sources.dfir import FEED_URL, SNAPSHOT, DfirConnector

FIX = Path(__file__).parent / "fixtures" / "dfir_feed.xml"
REPORT_ID = re.compile(r"^[a-z][a-z0-9-]*:\S+$")
URL = re.compile(r"^https?://\S+$")
BENGAL = "https://thedfirreport.com/2026/08/24/bengalseo-part-1-anatomy-of-the-operation/"
LYNX = "https://thedfirreport.com/2025/12/17/cats-got-your-files-lynx-ransomware/"


def rss(*items: str) -> bytes:
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            "<title>The DFIR Report</title><link>https://thedfirreport.com/home/</link>"
            + "".join(f"<item>{i}</item>" for i in items) + "</channel></rss>").encode("utf-8")


@pytest.fixture
def no_wait(monkeypatch):
    # test_http changes these module globals and never restores them, so every
    # test that goes through the client sets them itself.
    monkeypatch.setattr(http, "MIN_INTERVAL", 0)
    monkeypatch.setattr(http, "BACKOFF_BASE", 0)


def fetch_feed(store: SnapshotStore, body: bytes) -> None:
    with respx.mock:
        respx.get(FEED_URL).mock(return_value=httpx.Response(200, content=body))
        DfirConnector().fetch(store)


def saved_items(store: SnapshotStore) -> list[dict]:
    return json.loads(store.latest("dfir", SNAPSHOT).decode("utf-8"))


def seed(store: SnapshotStore, day: str, items: list[dict]) -> None:
    # Written by hand into an older dated folder, so a test can tell an old
    # snapshot from one saved today.
    d = store.root / "dfir" / day
    d.mkdir(parents=True)
    (d / SNAPSHOT).write_text(json.dumps(items), encoding="utf-8")


def test_is_a_connector_named_dfir():
    assert DfirConnector.name == "dfir"
    assert isinstance(DfirConnector(), Connector)


def test_snapshot_keeps_only_title_link_and_date(tmp_path, no_wait):
    s = SnapshotStore(tmp_path)
    fetch_feed(s, FIX.read_bytes())
    items = saved_items(s)
    assert items == [
        {"title": "BengalSEO Part 1: Anatomy of the Operation", "link": BENGAL, "published": "2026-08-24"},
        {"title": "Cat’s Got Your Files: Lynx Ransomware", "link": LYNX, "published": "2025-12-17"},
    ]


def test_no_body_text_reaches_the_snapshot(tmp_path, no_wait):
    # The DFIR Report reserves all rights to its text, so the source is
    # link-only. The excerpt, a full-content body, categories, author and
    # GUID must all stay out, and the raw XML is never saved.
    s = SnapshotStore(tmp_path)
    fetch_feed(s, FIX.read_bytes())
    raw = s.latest("dfir", SNAPSHOT)
    for marker in (b"EXCERPT-BODY-MARKER", b"FULLTEXT-BODY-MARKER", b"Case Summary",
                   b"content:encoded", b"<description>", b"scam", b"rdp", b"editor", b"?p=50572"):
        assert marker not in raw
    assert [p.name for p in (tmp_path / "dfir").rglob("*") if p.is_file()] == [SNAPSHOT]


def test_normalize_gives_link_only_reports(tmp_path, no_wait):
    s = SnapshotStore(tmp_path)
    fetch_feed(s, FIX.read_bytes())
    b = DfirConnector().normalize(s)
    assert b.source == "dfir" and b.campaigns == [] and b.actors == []
    [bengal, lynx] = b.reports
    assert (bengal.title, bengal.url, bengal.published) == (
        "BengalSEO Part 1: Anatomy of the Operation", BENGAL, "2026-08-24")
    assert lynx.title == "Cat’s Got Your Files: Lynx Ransomware"
    for r in b.reports:
        assert r.source == "dfir"
        assert r.date_basis == "publisher"
        assert r.organisation == "The DFIR Report"
        assert REPORT_ID.fullmatch(f"{r.source}:{r.source_id}")
        assert URL.fullmatch(r.url)
        # Titles and links are all a link-only source may give. Post
        # categories such as "akira" are not actor tags.
        assert r.actor_names == [] and r.cves == [] and r.techniques == []
        assert r.archive_url is None and r.sha1 is None
        assert r.retrieved_at == s.latest_date("dfir")


def test_posts_older_than_the_feed_window_are_kept(tmp_path, no_wait):
    # The feed lists only the newest posts, so each fetch merges with the
    # previous snapshot. A retitled post takes the feed's new title.
    s = SnapshotStore(tmp_path)
    old = {"title": "An older post", "link": "https://thedfirreport.com/2021/01/01/older/", "published": "2021-01-01"}
    retitled = {"title": "Old title", "link": "http://www.thedfirreport.com/2026/08/24/bengalseo-part-1-anatomy-of-the-operation",
                "published": "2026-08-24"}
    seed(s, "2000-01-01", [old, retitled])
    fetch_feed(s, FIX.read_bytes())
    items = saved_items(s)
    assert [i["link"] for i in items] == [BENGAL, LYNX, old["link"]]
    assert items[0]["title"] == "BengalSEO Part 1: Anatomy of the Operation"


@pytest.mark.parametrize("body", [rss(), b"<html><body>Service unavailable</body></html>", b""])
def test_an_empty_or_broken_feed_raises_and_keeps_the_last_snapshot(tmp_path, no_wait, body):
    # Merging would otherwise re-save the old items under today's date, and
    # the source would look fresh although the fetch failed.
    s = SnapshotStore(tmp_path)
    seed(s, "2000-01-01", [{"title": "An older post", "link": LYNX, "published": "2025-12-17"}])
    with pytest.raises(ValueError):
        fetch_feed(s, body)
    assert s.latest_date("dfir") == "2000-01-01"


def test_date_is_the_publishers_own_calendar_day(tmp_path, no_wait):
    # 21:30 at UTC-5 is already the next day in UTC. The post's own URL and
    # page carry the publisher's date, so that is the one kept.
    s = SnapshotStore(tmp_path)
    fetch_feed(s, rss("<title>Late post</title><link>https://thedfirreport.com/2025/08/05/late/</link>"
                      "<pubDate>Tue, 05 Aug 2025 21:30:00 -0500</pubDate>"))
    assert saved_items(s)[0]["published"] == "2025-08-05"


def test_a_post_without_a_usable_date_is_kept_as_undated(tmp_path, no_wait):
    s = SnapshotStore(tmp_path)
    fetch_feed(s, rss("<title>No date</title><link>https://thedfirreport.com/x/</link>",
                      "<title>Bad date</title><link>https://thedfirreport.com/y/</link><pubDate>soon</pubDate>"))
    reports = DfirConnector().normalize(s).reports
    assert {(r.title, r.published, r.date_basis) for r in reports} == {
        ("No date", None, "unknown"), ("Bad date", None, "unknown")}


def test_items_without_a_title_or_an_http_link_are_skipped_and_counted(tmp_path, no_wait, caplog):
    s = SnapshotStore(tmp_path)
    with caplog.at_level("WARNING"):
        fetch_feed(s, rss("<title>Kept</title><link>https://thedfirreport.com/kept/</link>",
                          "<title>  </title><link>https://thedfirreport.com/untitled/</link>",
                          "<title>No link</title>",
                          "<title>Odd link</title><link>javascript:alert(1)</link>"))
    assert [i["title"] for i in saved_items(s)] == ["Kept"]
    assert "dfir: dropped 3 feed items" in caplog.text


def test_a_damaged_stored_snapshot_is_cleaned_on_normalize(tmp_path, caplog):
    # An older or hand-edited snapshot is checked again rather than trusted.
    s = SnapshotStore(tmp_path)
    seed(s, "2000-01-01", [
        {"title": " Kept \n post ", "link": " https://thedfirreport.com/k/ ", "published": 20250101},
        {"title": "No link"}, "not an item", {"title": "Dated", "link": LYNX, "published": "2025-02-30"}])
    with caplog.at_level("WARNING"):
        reports = DfirConnector().normalize(s).reports
    assert [(r.title, r.url, r.published) for r in reports] == [
        ("Kept post", "https://thedfirreport.com/k/", None), ("Dated", LYNX, None)]
    assert "dfir: dropped 2 stored items" in caplog.text


def test_titles_are_single_trimmed_lines(tmp_path, no_wait):
    s = SnapshotStore(tmp_path)
    fetch_feed(s, rss("<title>\n  Two\n  lines &amp; spaces  </title><link>https://thedfirreport.com/t/</link>"))
    assert DfirConnector().normalize(s).reports[0].title == "Two lines & spaces"


def test_a_title_marked_up_as_html_becomes_plain_text(tmp_path, no_wait):
    # feedparser hands back escaped markup in a title as HTML. The site shows
    # titles as text, so tags go and entities are decoded once.
    s = SnapshotStore(tmp_path)
    fetch_feed(s, rss("<title>A &lt;b&gt;bold&lt;/b&gt; &amp;amp; move</title><link>https://thedfirreport.com/b/</link>"))
    assert saved_items(s)[0]["title"] == "A bold & move"


def test_source_id_comes_from_the_normalized_link(tmp_path, no_wait):
    # The ID must not change when the feed switches between http, https and
    # www., and it avoids slashes so it can sit in a URL fragment or a key.
    s = SnapshotStore(tmp_path)
    fetch_feed(s, FIX.read_bytes())
    ids = [r.source_id for r in DfirConnector().normalize(s).reports]
    assert ids == ["2026-08-24-bengalseo-part-1-anatomy-of-the-operation",
                   "2025-12-17-cats-got-your-files-lynx-ransomware"]


def test_a_repeated_link_is_kept_once(tmp_path, no_wait):
    s = SnapshotStore(tmp_path)
    fetch_feed(s, rss("<title>First</title><link>https://thedfirreport.com/same/</link>",
                      "<title>Second</title><link>http://www.thedfirreport.com/same</link>"))
    assert [r.title for r in DfirConnector().normalize(s).reports] == ["First"]


def test_no_snapshot_gives_an_empty_bundle(tmp_path):
    b = DfirConnector().normalize(SnapshotStore(tmp_path))
    assert b.source == "dfir" and b.reports == []
