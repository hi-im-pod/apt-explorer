"""ORKL, the community cyber threat intelligence library, through its API only.

ORKL is link-only under SOURCES.md while a permission request is pending. A
published report carries only its own title, publisher, publication date and
links, plus the CVE and technique IDs this project finds in the text itself.

Report text is read once, during fetch(), for that regex pass, and is never
stored: each snapshot line is derived from the entry and has no plain_text.

ORKL's threat-actor tags are kept in the snapshot as matching evidence, so the
policy can flip without a refetch if ORKL agrees. While ORKL is link-only,
normalize() leaves every report's actor_names empty. The resolver reads the
tags through actor_tags() instead, and a tag alone never links a report to an
actor on the site.
"""
import json
import logging
import re
from urllib.parse import quote

from aptx.core import http
from aptx.core.dates import resolve_report_date
from aptx.core.models import ReportRecord, SourceBundle
from aptx.core.snapshot import SnapshotStore
from aptx.extract.ids import find_cves, technique_candidates
from aptx.sources.base import Connector, publish_policy

log = logging.getLogger(__name__)

NAME = "orkl"
API = "https://orkl.eu/api/v1"
ENTRIES = "entries.jsonl"
PAGE_SIZE = 100
PROGRESS_EVERY = 25          # pages, about 2,500 entries
# A first backfill that ends short of this share of ORKL's own count is not
# saved. Weekly runs stop at the first entry they already hold, so they trust
# the snapshot to contain every older entry; a truncated backfill saved once
# would leave a gap that no later run fills.
MIN_COVERAGE = 0.9
# Policies under which ORKL's actor tags may be shown on reports. Link-only
# and evidence-only keep them internal.
TAGS_SHOWN = frozenset({"full", "derived-only"})

_SHA1 = re.compile(r"[0-9a-f]{40}")
_HTTP_URL = re.compile(r"https?://\S+")
# Every ASCII character a URL may carry unescaped, plus "%" for existing escapes.
_URL_SAFE = "%:/?#[]@!$&'()*+,;=~-._"


def _text(value) -> str | None:
    """A trimmed single line, or None when nothing is left."""
    text = " ".join(value.split()) if isinstance(value, str) else ""
    return text or None


def _strings(values) -> list[str]:
    # ORKL sends null instead of an empty list, so every list goes through here.
    return [v.strip() for v in values or [] if isinstance(v, str) and v.strip()]


def _http_url(value) -> str | None:
    # The contract accepts only http and https links, and a published link
    # must open in a browser. ORKL's vx-underground references, about a third
    # of the library, carry raw spaces and curly quotes in the path. Browsers
    # send those percent-encoded, so encoding them here keeps the link working
    # and inside the contract's no-whitespace pattern. "%" is left alone so
    # an escape that is already there is not encoded twice.
    text = value.strip() if isinstance(value, str) else ""
    if not re.match(r"https?://", text):
        return None
    text = quote(text, safe=_URL_SAFE)
    return text if _HTTP_URL.fullmatch(text) else None


def _read_lines(store: SnapshotStore) -> list[dict]:
    """The derived snapshot lines, newest first, skipping malformed ones."""
    raw = store.latest(NAME, ENTRIES)
    if raw is None:
        return []
    lines, dropped = [], 0
    for line in raw.decode("utf-8-sig").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            dropped += 1
            continue
        if isinstance(entry, dict) and isinstance(entry.get("id"), str) and entry["id"]:
            lines.append(entry)
        else:
            dropped += 1
    if dropped:
        # Malformed lines are dropped one by one and counted, never silently.
        log.warning("orkl: dropped %d malformed snapshot lines", dropped)
    return lines


def actor_tags(store: SnapshotStore) -> dict[str, list[dict]]:
    """ORKL's threat-actor tags per entry ID, as matching evidence for the resolver.

    Each tag is {main_name, aliases, source_name}. The keys are ORKL entry IDs,
    the same values as ReportRecord.source_id. Entries without tags are left
    out. SOURCES.md forbids showing these tags, or using them alone to attach
    a report to an actor, while ORKL is link-only.
    """
    return {e["id"]: e["threat_actors"] for e in _read_lines(store) if e.get("threat_actors")}


def _title(entry: dict, url: str | None) -> str:
    """The report's own title, or the next most faithful name for it.

    About one entry in ten has an empty title. ORKL's llm_title is skipped on
    purpose: ORKL generated it, so it is not the report's own title, and a
    link-only source may publish only the report's own metadata. The file
    name the report was published under comes next, then its URL.
    """
    for candidate in [entry.get("title"), *_strings(entry.get("report_names")), url, entry.get("sha1")]:
        text = _text(candidate)
        if text:
            return text
    return entry["id"]


class OrklConnector(Connector):
    name = NAME

    @staticmethod
    def _derive(entry: dict) -> dict:
        """One snapshot line: the entry's metadata plus the IDs found in its text.

        The regex pass runs here, on plain_text, and the text is not copied
        into the line, so no report text is ever stored.
        """
        entry_id = entry.get("id")
        if not isinstance(entry_id, str) or not entry_id.strip():
            raise ValueError("orkl: entry without an id")
        text = entry.get("plain_text") if isinstance(entry.get("plain_text"), str) else ""
        sha1 = (entry.get("sha1_hash") or "").strip().lower() if isinstance(entry.get("sha1_hash"), str) else ""
        files = entry.get("files") if isinstance(entry.get("files"), dict) else {}
        tags = []
        for tag in entry.get("threat_actors") or []:
            main = _text(tag.get("main_name")) if isinstance(tag, dict) else None
            if main:
                tags.append({"main_name": main, "aliases": _strings(tag.get("aliases")),
                             "source_name": _text(tag.get("source_name"))})
        return {
            "id": entry_id.strip(),
            "sha1": sha1 if _SHA1.fullmatch(sha1) else None,
            "title": entry.get("title") if isinstance(entry.get("title"), str) else "",
            "report_names": _strings(entry.get("report_names")),
            "authors": entry.get("authors") if isinstance(entry.get("authors"), str) else "",
            "created_at": entry.get("created_at"),
            "file_creation_date": entry.get("file_creation_date"),
            "references": _strings(entry.get("references")),
            "sources": _strings(entry.get("sources")),
            "threat_actors": tags,
            "files": {k: files[k] for k in ("pdf", "text") if isinstance(files.get(k), str)},
            "cves": find_cves(text),
            # Every well-formed ID is kept; normalize() publishes only those
            # the current ATT&CK release defines, so an ATT&CK update applies
            # to old entries without refetching them.
            "techniques_raw": technique_candidates(text),
        }

    def fetch(self, store: SnapshotStore) -> None:
        """Page through the library, newest first, and save entries.jsonl.

        A weekly run stops at the first entry the last snapshot already holds
        and appends the older lines from it, so only new entries are fetched.
        That also means changes ORKL makes to an older entry, such as new tags,
        are not picked up; deleting the snapshot forces a full backfill.
        Nothing is saved when the run fails part-way, or when a weekly run
        never reaches a known entry.
        """
        info = http.get_json(f"{API}/library/info")
        data = info.get("data") if isinstance(info, dict) else None
        total = data.get("library_entries") if isinstance(data, dict) else None
        # Without a count the coverage check below is skipped, not failed.
        total = total if isinstance(total, int) and total > 0 else 0
        previous = _read_lines(store)
        known = {e["id"] for e in previous}

        fresh: list[dict] = []
        seen: set[str] = set()
        offset = pages = dropped = 0
        while True:
            body = http.get_json(f"{API}/library/entries", params={
                "limit": PAGE_SIZE, "offset": offset, "order_by": "created_at", "order": "desc"})
            # An empty page comes back as "data": null, not [].
            page = (body.get("data") if isinstance(body, dict) else None) or []
            if not isinstance(page, list):
                raise ValueError(f"orkl: entries page at offset {offset} is not a list")
            reached_known = False
            added = 0
            for entry in page:
                if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"].strip():
                    dropped += 1
                    continue
                entry_id = entry["id"].strip()
                if entry_id in known:
                    reached_known = True
                    break
                # Entries added while paging shift later pages, so an entry
                # can arrive twice.
                if entry_id not in seen:
                    seen.add(entry_id)
                    fresh.append(self._derive(entry))
                    added += 1
            pages += 1
            if pages % PROGRESS_EVERY == 0:
                log.info("orkl: %d pages, %d new entries of %d", pages, len(fresh), total)
            if reached_known or len(page) < PAGE_SIZE:
                break
            if added == 0:
                # A full page with nothing new means the server is repeating
                # itself, for example by ignoring the offset.
                log.warning("orkl: page at offset %d repeated earlier entries; stopping", offset)
                break
            offset += PAGE_SIZE

        if dropped:
            log.warning("orkl: dropped %d entries without an id", dropped)
        if previous and not reached_known:
            # A weekly run must meet an entry it already holds; that is what
            # proves the answer was complete. An empty or truncated answer
            # would otherwise re-save the old lines under today's date, and
            # the source would look fresh when it was not fetched at all.
            raise ValueError(f"orkl: paging ended after {len(fresh)} new entries without reaching "
                             "a known entry; snapshot not saved")
        fresh_ids = {e["id"] for e in fresh}
        combined = fresh + [e for e in previous if e["id"] not in fresh_ids]
        if not combined:
            raise ValueError("orkl: the library returned no entries")
        if total and len(combined) < total * MIN_COVERAGE:
            raise ValueError(f"orkl: only {len(combined)} of {total} entries fetched; snapshot not saved")
        log.info("orkl: %d new entries, %d in the snapshot", len(fresh), len(combined))
        payload = "".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in combined)
        store.save(self.name, ENTRIES, payload.encode("utf-8"))

    def normalize(self, store: SnapshotStore, valid_techniques: set[str] | frozenset[str] = frozenset(),
                  lib_dates: dict[str, str] | None = None) -> SourceBundle:
        """One ReportRecord per snapshot line.

        valid_techniques is the set of ATT&CK technique IDs, and lib_dates is
        malpedia.library_dates(). The CLI passes both, because connectors
        never import each other. Without them no technique is published and
        no report is dated from the Malpedia library.
        """
        lines = _read_lines(store)
        if not lines:
            return SourceBundle(source=self.name)
        # The records are only as fresh as the snapshot. After a failed fetch
        # that snapshot is older than today, and the date must say so.
        retrieved_at = store.latest_date(self.name)
        # Read once per run, not per record. The tags stay internal unless
        # SOURCES.md is changed to allow them.
        show_tags = publish_policy(self.name) in TAGS_SHOWN
        lib_dates = lib_dates or {}

        reports = []
        for e in lines:
            urls = [u for u in (_http_url(r) for r in e.get("references") or []) if u]
            url = urls[0] if urls else None
            published, basis = resolve_report_date(urls, lib_dates, e.get("file_creation_date"), e.get("created_at"))
            files = e.get("files") or {}
            names = []
            if show_tags:
                names = list(dict.fromkeys(t["main_name"] for t in e.get("threat_actors") or []))
            reports.append(ReportRecord(
                source=self.name,
                source_id=e["id"],
                title=_title(e, url),
                published=published,
                date_basis=basis,
                organisation=_text(e.get("authors")),
                url=url,
                # ORKL's archived copy is a fallback link for a dead original,
                # not re-hosted content.
                archive_url=_http_url(files.get("pdf")),
                sha1=e.get("sha1"),
                actor_names=names,
                cves=list(e.get("cves") or []),
                techniques=[t for t in e.get("techniques_raw") or [] if t in valid_techniques],
                retrieved_at=retrieved_at,
            ))
        return SourceBundle(source=self.name, reports=reports)
