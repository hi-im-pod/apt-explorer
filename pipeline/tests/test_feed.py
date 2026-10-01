import json

import httpx
import pytest
import respx

from aptx.core import http
from aptx.core.snapshot import SnapshotStore
from aptx.sources.feed import SNAPSHOT, FeedConnector
from aptx.sources.vendors import EsetConnector, MicrosoftBlogConnector, TalosConnector

URL = "https://blog.example.test/feed/"


class Paged(FeedConnector):
    name = "paged"
    feed_url = URL
    organisation = "Example Labs"
    host = "blog.example.test"
    page_param = "paged"
    max_pages = 6


class Flat(FeedConnector):
    name = "flat"
    feed_url = URL
    organisation = "Example Labs"
    host = "blog.example.test"


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(http, "MIN_INTERVAL", 0)
    monkeypatch.setattr(http, "BACKOFF_BASE", 0)


def post(n: int) -> str:
    return (f"<item><title>Post {n}</title><link>https://blog.example.test/2026/{n}/</link>"
            f"<pubDate>Mon, 01 Jun 2026 10:00:00 +0000</pubDate></item>")


def rss(*numbers: int) -> bytes:
    return ('<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>x</title>'
            "<link>https://blog.example.test/</link>" + "".join(post(n) for n in numbers)
            + "</channel></rss>").encode("utf-8")


def serve(pages: dict[int, bytes | int]):
    """Mock the feed. An int answers with that status, a page not listed with 404."""
    requested: list[int] = []

    def answer(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params.get("paged", "1"))
        requested.append(page)
        body = pages.get(page, 404)
        return httpx.Response(body) if isinstance(body, int) else httpx.Response(200, content=body)

    respx.get(URL).mock(side_effect=answer)
    return requested


def seed(store: SnapshotStore, numbers: list[int]) -> None:
    d = store.root / "paged" / "2000-01-01"
    d.mkdir(parents=True)
    items = [{"title": f"Post {n}", "link": f"https://blog.example.test/2026/{n}/", "published": "2026-06-01"}
             for n in numbers]
    (d / SNAPSHOT).write_text(json.dumps(items), encoding="utf-8")


def titles(store: SnapshotStore, name: str = "paged") -> list[str]:
    return [i["title"] for i in json.loads(store.latest(name, SNAPSHOT).decode("utf-8"))]


@respx.mock
def test_older_pages_are_read_until_one_is_missing(tmp_path):
    requested = serve({1: rss(1, 2), 2: rss(3, 4), 3: rss(5)})
    s = SnapshotStore(tmp_path)
    Paged().fetch(s)
    assert titles(s) == ["Post 1", "Post 2", "Post 3", "Post 4", "Post 5"]
    assert requested == [1, 2, 3, 4]


@respx.mock
def test_a_page_with_no_items_ends_the_scan(tmp_path):
    requested = serve({1: rss(1), 2: rss(2), 3: rss()})
    s = SnapshotStore(tmp_path)
    Paged().fetch(s)
    assert titles(s) == ["Post 1", "Post 2"] and requested == [1, 2, 3]


@respx.mock
def test_a_server_that_repeats_the_last_page_does_not_loop(tmp_path):
    requested = serve({1: rss(1, 2), 2: rss(3), 3: rss(3), 4: rss(3)})
    s = SnapshotStore(tmp_path)
    Paged().fetch(s)
    assert titles(s) == ["Post 1", "Post 2", "Post 3"] and requested == [1, 2, 3]


@respx.mock
def test_a_backfill_runs_even_when_page_one_is_all_known(tmp_path):
    # The gap case: an earlier fetch kept only the newest page, so page 1 adds
    # nothing and the older posts sit on page 2 onward.
    requested = serve({1: rss(1, 2), 2: rss(3, 4), 3: rss(5)})
    s = SnapshotStore(tmp_path)
    seed(s, [1, 2])
    Paged().fetch(s)
    assert titles(s) == ["Post 1", "Post 2", "Post 3", "Post 4", "Post 5"]
    assert requested == [1, 2, 3, 4]


@respx.mock
def test_a_complete_snapshot_costs_two_requests(tmp_path):
    requested = serve({1: rss(1, 2), 2: rss(3, 4), 3: rss(5)})
    s = SnapshotStore(tmp_path)
    seed(s, [1, 2, 3, 4, 5])
    Paged().fetch(s)
    assert requested == [1, 2]
    assert len(titles(s)) == 5


@respx.mock
def test_a_failure_part_way_keeps_the_pages_already_read(tmp_path, caplog):
    serve({1: rss(1), 2: rss(2), 3: 500})
    s = SnapshotStore(tmp_path)
    with caplog.at_level("WARNING"):
        Paged().fetch(s)
    assert titles(s) == ["Post 1", "Post 2"]
    assert "paged: page 3 failed" in caplog.text


@respx.mock
def test_a_failure_on_page_one_still_raises(tmp_path):
    serve({1: 500})
    with pytest.raises(httpx.HTTPStatusError):
        Paged().fetch(SnapshotStore(tmp_path))


@respx.mock
def test_the_page_cap_stops_a_feed_that_never_ends(tmp_path, caplog):
    pages = {n: rss(n) for n in range(1, 50)}
    requested = serve(pages)
    s = SnapshotStore(tmp_path)
    with caplog.at_level("WARNING"):
        Paged().fetch(s)
    assert requested == [1, 2, 3, 4, 5, 6]
    assert "stopped at the 6-page cap" in caplog.text


@respx.mock
def test_a_feed_without_a_page_parameter_is_read_once(tmp_path):
    requested = serve({1: rss(1, 2), 2: rss(3)})
    s = SnapshotStore(tmp_path)
    Flat().fetch(s)
    assert titles(s, "flat") == ["Post 1", "Post 2"] and requested == [1]


@respx.mock
def test_normalize_uses_the_subclass_name_organisation_and_host(tmp_path):
    serve({1: rss(1)})
    s = SnapshotStore(tmp_path)
    Flat().fetch(s)
    b = Flat().normalize(s)
    [r] = b.reports
    assert (b.source, r.source, r.organisation, r.source_id) == ("flat", "flat", "Example Labs", "2026-1")
    assert r.actor_names == [] and r.cves == [] and r.date_basis == "publisher"


VENDORS = [
    (TalosConnector, "talos", "Cisco Talos", "blog.talosintelligence.com"),
    (EsetConnector, "eset", "ESET Research", "welivesecurity.com"),
    (MicrosoftBlogConnector, "microsoftblog", "Microsoft Security", "microsoft.com"),
]


@pytest.mark.parametrize("cls,name,organisation,host", VENDORS)
def test_each_vendor_feed_is_link_only_and_reads_one_page(cls, name, organisation, host):
    c = cls()
    assert (c.name, c.organisation, c.host) == (name, organisation, host)
    assert c.feed_url.startswith("https://") and host in c.feed_url
    # None of the feeds keeps older pages.
    assert c.page_param is None


@respx.mock
def test_a_vendor_post_is_a_report_with_the_vendor_as_organisation(tmp_path):
    body = ('<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>'
            "<item><title>Backdoors in the wild</title>"
            "<link>https://blog.talosintelligence.com/backdoors-in-the-wild/</link>"
            "<pubDate>Fri, 18 Sep 2026 10:00:00 +0000</pubDate>"
            "<description>The full text, never kept.</description><category>APT</category></item>"
            "</channel></rss>").encode("utf-8")
    respx.get(TalosConnector.feed_url).mock(return_value=httpx.Response(200, content=body))
    s = SnapshotStore(tmp_path)
    TalosConnector().fetch(s)
    assert b"never kept" not in s.latest("talos", SNAPSHOT) and b"APT" not in s.latest("talos", SNAPSHOT)
    [r] = TalosConnector().normalize(s).reports
    assert (r.source, r.source_id, r.organisation, r.published) == (
        "talos", "backdoors-in-the-wild", "Cisco Talos", "2026-09-18")
    assert r.actor_names == [] and r.cves == []


def _eset_feed(*slugs: str) -> bytes:
    items = "".join(f"<item><title>{p}</title><link>https://www.welivesecurity.com/en/{p}/post/</link>"
                    "<pubDate>Mon, 01 Jun 2026 10:00:00 +0000</pubDate></item>" for p in slugs)
    return ('<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>' + items
            + "</channel></rss>").encode("utf-8")


@respx.mock
def test_eset_keeps_only_research_posts_including_ones_already_stored(tmp_path):
    respx.get(EsetConnector.feed_url).mock(
        return_value=httpx.Response(200, content=_eset_feed("eset-research", "scams", "business-security")))
    s = SnapshotStore(tmp_path)
    # An older snapshot, taken before the filter existed, held a scam post.
    d = s.root / "eset" / "2000-01-01"
    d.mkdir(parents=True)
    (d / SNAPSHOT).write_text(json.dumps([
        {"title": "old scam", "link": "https://www.welivesecurity.com/en/scams/old/", "published": "2026-01-01"},
        {"title": "old research", "link": "https://www.welivesecurity.com/en/eset-research/old/", "published": "2026-01-01"},
    ]), encoding="utf-8")
    EsetConnector().fetch(s)
    assert titles(s, "eset") == ["eset-research", "old research"]
    assert [r.title for r in EsetConnector().normalize(s).reports] == ["eset-research", "old research"]


@respx.mock
def test_a_feed_with_no_research_posts_is_not_an_error(tmp_path):
    respx.get(EsetConnector.feed_url).mock(return_value=httpx.Response(200, content=_eset_feed("scams")))
    s = SnapshotStore(tmp_path)
    EsetConnector().fetch(s)
    assert titles(s, "eset") == [] and EsetConnector().normalize(s).reports == []
