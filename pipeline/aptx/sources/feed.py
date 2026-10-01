"""A publisher's RSS feed, kept as titles, dates and links only.

Several publishers reserve their text, and SOURCES.md lists their feeds as
link-only. A snapshot therefore keeps three fields per post: title, link and
published date. The raw feed, with its excerpts, categories and authors, is
parsed in memory and never saved.

One subclass per publisher sets the class attributes below. Each publisher is
its own source, so each has its own SOURCES.md row, notice entry and policy.
"""
import html
import json
import logging
import re
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import feedparser
import httpx

from aptx.core import http
from aptx.core.dates import parse_date
from aptx.core.models import ReportRecord, SourceBundle
from aptx.core.snapshot import SnapshotStore
from aptx.core.urls import norm_url
from aptx.sources.base import Connector

log = logging.getLogger(__name__)

SNAPSHOT = "posts.json"

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
        return parsedate_to_datetime(raw).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return parse_date(raw)


def _http_url(value: str) -> str:
    """The link with a lower-case scheme, or "" unless it is an http(s) URL.

    The contract's URL pattern is case-sensitive, so HTTPS:// would pass here
    and then fail schema validation at build time, which blocks the whole
    data commit. Any other scheme, such as javascript:, is refused.
    """
    m = _HTTP_URL.fullmatch(value.strip())
    return m.group(1).lower() + m.group(2) if m else ""


def feed_items(payload: bytes, name: str) -> list[dict]:
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
        log.warning("%s: dropped %d feed items without a title or an http link", name, dropped)
    return items


def stored_items(store: SnapshotStore, name: str) -> list[dict]:
    """The newest snapshot's items, cleaned the same way as fresh feed items.

    Older snapshots may predate a rule or have been edited by hand, so every
    item is checked again. Unusable items are dropped and counted.
    """
    raw = store.latest(name, SNAPSHOT)
    if raw is None:
        return []
    items, dropped = [], 0
    for i in json.loads(raw.decode("utf-8")):
        title = _one_line(str(i.get("title") or "")) if isinstance(i, dict) else ""
        link = _http_url(str(i.get("link") or "")) if isinstance(i, dict) else ""
        if not (title and link):
            dropped += 1
            continue
        published = parse_date(str(i.get("published") or ""))
        items.append({"title": title, "link": link, "published": published})
    if dropped:
        log.warning("%s: dropped %d stored items without a title or an http link", name, dropped)
    return items


def merge(new: list[dict], old: list[dict]) -> list[dict]:
    """The feed's items in feed order, then older items the feed no longer lists.

    A feed shows only the newest posts, so without the merge each fetch would
    forget everything older. Items are matched by norm_url, so a post whose
    link changed from http to https or gained a www. is kept once, and the
    feed's current title and link win over the stored ones.
    """
    merged: dict[str, dict] = {}
    for item in new + old:
        merged.setdefault(norm_url(item["link"]), item)
    return list(merged.values())


class FeedConnector(Connector):
    """Subclasses set name, feed_url, organisation and host.

    page_param names the query parameter that pages through older posts
    (WordPress feeds use "paged"). Leave it empty for a feed that has no
    older pages.
    """
    name: str
    feed_url: str
    organisation: str
    host: str
    page_param: str | None = None
    # When set, only posts whose link path starts with this prefix are kept, for
    # a feed that mixes the publisher's research with other kinds of post.
    path_prefix: str = ""
    # A cap on one fetch, so a feed that never runs out cannot loop. The cap is
    # logged when it is hit.
    max_pages: int = 100

    def accepts(self, link: str) -> bool:
        return urlsplit(link).path.startswith(self.path_prefix)

    def _kept(self, items: list[dict]) -> list[dict]:
        return [i for i in items if self.accepts(i["link"])]

    def _older_pages(self, seen: set[str]) -> list[dict]:
        """Items from pages 2 onward, until a page adds nothing not already seen.

        Page 2 is always read, even when page 1 held only known posts, because
        posts that fell off page 1 between two fetches would otherwise stay
        missing. The scan stops at the first page that adds nothing new, a 404,
        or a page with no items. A failure part-way keeps what was read, since
        the older posts are a bonus and page 1 already succeeded.
        """
        found: list[dict] = []
        for page in range(2, self.max_pages + 1):
            try:
                payload = http.get_bytes(f"{self.feed_url}?{self.page_param}={page}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 404:
                    log.warning("%s: page %d failed (%s); keeping the pages read so far", self.name, page, e)
                return found
            except httpx.TransportError as e:
                log.warning("%s: page %d failed (%s); keeping the pages read so far", self.name, page, e)
                return found
            fresh = [i for i in self._kept(feed_items(payload, self.name)) if norm_url(i["link"]) not in seen]
            if not fresh:
                return found
            seen.update(norm_url(i["link"]) for i in fresh)
            found.extend(fresh)
        log.warning("%s: stopped at the %d-page cap", self.name, self.max_pages)
        return found

    def fetch(self, store: SnapshotStore) -> None:
        items = feed_items(http.get_bytes(self.feed_url), self.name)
        if not items:
            # An empty feed or an error page answered with 200 must not be
            # merged and re-saved under today's date, or the source would
            # look fresh although nothing new arrived. Raising lets the CLI
            # mark it stale and keep the last good snapshot.
            raise ValueError(f"The {self.organisation} feed has no usable items")
        # The feed check above counts every post; the filter applies after it,
        # to the new items and to the older snapshot alike.
        items = self._kept(items)
        old = self._kept(stored_items(store, self.name))
        if self.page_param:
            seen = {norm_url(i["link"]) for i in old} | {norm_url(i["link"]) for i in items}
            items = items + self._older_pages(seen)
        merged = merge(items, old)
        store.save(self.name, SNAPSHOT, json.dumps(merged, ensure_ascii=False, indent=1).encode("utf-8"))

    def _source_id(self, link: str) -> str:
        # Built from the normalized link so http, https and www. variants give
        # one ID. The site's own host is dropped and slashes become hyphens, which
        # turns ".../2026/08/24/slug/" into "2026-08-24-slug" and keeps the ID
        # usable as a key or a URL fragment.
        key = norm_url(link)
        host, _, path = key.partition("/")
        return (path if host == self.host and path else key).replace("/", "-")

    def normalize(self, store: SnapshotStore) -> SourceBundle:
        if store.latest(self.name, SNAPSHOT) is None:
            return SourceBundle(source=self.name)
        # The records are only as fresh as the snapshot, which is older than
        # today when this week's fetch failed.
        retrieved_at = store.latest_date(self.name)
        reports: dict[str, ReportRecord] = {}
        for item in self._kept(stored_items(store, self.name)):
            sid = self._source_id(item["link"])
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
                organisation=self.organisation,
                url=item["link"].strip(),
                retrieved_at=retrieved_at,
            )
        # Every post is a report. Campaigns stay empty, and post categories
        # are never read as actor tags.
        return SourceBundle(source=self.name, reports=list(reports.values()))
