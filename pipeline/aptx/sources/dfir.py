"""The DFIR Report's RSS feed, as titles, dates and links only.

The DFIR Report reserves all rights to its text, and SOURCES.md lists it as
link-only. The snapshot therefore keeps three fields per post: title, link and
published date. The raw feed, with its excerpts, categories and authors, is
parsed in memory and never saved.
"""
import html
import json
import logging
import re
from datetime import date
from email.utils import parsedate_to_datetime

import feedparser

from aptx.core import http
from aptx.core.dates import parse_date
from aptx.core.models import ReportRecord, SourceBundle
from aptx.core.snapshot import SnapshotStore
from aptx.core.urls import norm_url
from aptx.sources.base import Connector

log = logging.getLogger(__name__)

FEED_URL = "https://thedfirreport.com/feed/"
SNAPSHOT = "posts.json"
ORGANISATION = "The DFIR Report"
HOST = "thedfirreport.com"

_HTTP_URL = re.compile(r"(https?)(://\S+)", re.IGNORECASE)
_TAG = re.compile(r"<[^>]*>")


def _one_line(text: str) -> str:
    # Published labels are single trimmed lines, and feeds wrap long titles.
    return " ".join(text.split())


def _title(entry) -> str:
    title = entry.get("title") or ""
    # feedparser decodes a plain-text title itself, but returns a title that
    # contains escaped markup as HTML. The site shows titles as text, so the
    # tags go and the entities are decoded once.
    if (entry.get("title_detail") or {}).get("type") == "text/html":
        title = html.unescape(_TAG.sub("", title))
    return _one_line(title)


def _calendar_day(day: str | None) -> str | None:
    # parse_date does not yet check that the month and day exist, so a value
    # such as 2025-02-30 is refused here rather than reaching the site.
    try:
        return date.fromisoformat(day).isoformat() if day else None
    except ValueError:
        return None


def _published(raw: str | None) -> str | None:
    """The post's date as the publisher wrote it, or None when unusable.

    feedparser's parsed date is converted to UTC, which moves an evening post
    in the Americas to the next day. The publisher's own calendar day is the
    one printed on the post and in its URL, so the RFC 822 value is read in
    its own offset. Atom-style ISO dates fall through to parse_date.
    """
    if not raw:
        return None
    try:
        return _calendar_day(parsedate_to_datetime(raw).date().isoformat())
    except (TypeError, ValueError, IndexError):
        return _calendar_day(parse_date(raw))


def _http_url(value: str) -> str:
    """The link with a lower-case scheme, or "" unless it is an http(s) URL.

    The contract's URL pattern is case-sensitive, so HTTPS:// would pass here
    and then fail schema validation at build time, which blocks the whole
    data commit. Any other scheme, such as javascript:, is refused.
    """
    m = _HTTP_URL.fullmatch(value.strip())
    return m.group(1).lower() + m.group(2) if m else ""


def _feed_items(payload: bytes) -> list[dict]:
    # The payload goes to feedparser as bytes. Given a str, feedparser may
    # treat it as a URL or a path and fetch it itself, outside the polite
    # client.
    items, dropped = [], 0
    for entry in feedparser.parse(payload).entries:
        title, link = _title(entry), _http_url(entry.get("link") or "")
        if title and link:
            items.append({"title": title, "link": link, "published": _published(entry.get("published"))})
        else:
            dropped += 1
    if dropped:
        # Dropped items are counted, never skipped silently, so a change in
        # the feed shows up in the build log.
        log.warning("dfir: dropped %d feed items without a title or an http link", dropped)
    return items


def _stored_items(store: SnapshotStore) -> list[dict]:
    """The newest snapshot's items, cleaned the same way as fresh feed items.

    Older snapshots may predate a rule or have been edited by hand, so every
    item is checked again. Unusable items are dropped and counted.
    """
    raw = store.latest("dfir", SNAPSHOT)
    if raw is None:
        return []
    items, dropped = [], 0
    for i in json.loads(raw.decode("utf-8")):
        title = _one_line(str(i.get("title") or "")) if isinstance(i, dict) else ""
        link = _http_url(str(i.get("link") or "")) if isinstance(i, dict) else ""
        if not (title and link):
            dropped += 1
            continue
        published = _calendar_day(parse_date(str(i.get("published") or "")))
        items.append({"title": title, "link": link, "published": published})
    if dropped:
        log.warning("dfir: dropped %d stored items without a title or an http link", dropped)
    return items


def _merge(new: list[dict], old: list[dict]) -> list[dict]:
    """The feed's items in feed order, then older items the feed no longer lists.

    The feed shows only the newest posts, so without the merge each fetch
    would forget everything older. Items are matched by norm_url, so a post
    whose link changed from http to https or gained a www. is kept once, and
    the feed's current title and link win over the stored ones.
    """
    merged: dict[str, dict] = {}
    for item in new + old:
        merged.setdefault(norm_url(item["link"]), item)
    return list(merged.values())


def _source_id(link: str) -> str:
    # Built from the normalized link so http, https and www. variants give
    # one ID. The site's own host is dropped and slashes become hyphens, which
    # turns ".../2026/08/24/slug/" into "2026-08-24-slug" and keeps the ID
    # usable as a key or a URL fragment.
    key = norm_url(link)
    host, _, path = key.partition("/")
    return (path if host == HOST and path else key).replace("/", "-")


class DfirConnector(Connector):
    name = "dfir"

    def fetch(self, store: SnapshotStore) -> None:
        items = _feed_items(http.get_bytes(FEED_URL))
        if not items:
            # An empty feed or an error page answered with 200 must not be
            # merged and re-saved under today's date, or the source would
            # look fresh although nothing new arrived. Raising lets the CLI
            # mark it stale and keep the last good snapshot.
            raise ValueError("The DFIR Report feed has no usable items")
        merged = _merge(items, _stored_items(store))
        store.save(self.name, SNAPSHOT, json.dumps(merged, ensure_ascii=False, indent=1).encode("utf-8"))

    def normalize(self, store: SnapshotStore) -> SourceBundle:
        if store.latest(self.name, SNAPSHOT) is None:
            return SourceBundle(source=self.name)
        # The records are only as fresh as the snapshot, which is older than
        # today when this week's fetch failed.
        retrieved_at = store.latest_date(self.name)
        reports: dict[str, ReportRecord] = {}
        for item in _stored_items(store):
            sid = _source_id(item["link"])
            if sid in reports:
                continue
            published = item["published"]
            reports[sid] = ReportRecord(
                source=self.name,
                source_id=sid,
                title=item["title"],
                published=published,
                # The contract ties a null date to the "unknown" basis, so a
                # post without a usable date says so instead of claiming the
                # publisher dated it.
                date_basis="publisher" if published else "unknown",
                organisation=ORGANISATION,
                url=item["link"].strip(),
                retrieved_at=retrieved_at,
            )
        # Every DFIR post is a report in v1. Campaigns stay empty, and post
        # categories are never read as actor tags.
        return SourceBundle(source=self.name, reports=list(reports.values()))
