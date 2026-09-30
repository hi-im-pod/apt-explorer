"""Malpedia: actors, malware families and the dated report library.

Malpedia is derived-only under SOURCES.md. Names, aliases, country and sector
values, sponsors and family names may be published, but its description text
never is, so normalize() never reads it. Every endpoint used here is marked
"Access limitation: none", and the connector sends no API token, so no
restricted (TLP:AMBER) material enters a snapshot.

Two lookups serve other steps rather than this connector's own records:
- library_dates() dates reports from other sources, such as ORKL, by URL.
- report_links() maps a report URL to the actor names Malpedia attributes it
  to, which is one of the few publishable ways to link a report to an actor.
The CLI should pass them on only while publish_policy("malpedia") is not
"evidence-only", because a date or a link taken from Malpedia is itself
Malpedia data.
"""
import json
import logging
import re
from collections import defaultdict
from urllib.parse import quote

import httpx

from aptx.core import http
from aptx.core.dates import parse_date
from aptx.core.models import ActorRecord, SoftwareRecord, SourceBundle
from aptx.core.snapshot import SnapshotStore
# Re-exported, not redefined: the library side and the report side of every
# URL join must share one normalizer, or matching reports never meet.
from aptx.core.urls import norm_url
from aptx.sources.base import Connector

__all__ = ["MalpediaConnector", "actor_id", "library_dates", "norm_url", "parse_bib", "report_links"]

log = logging.getLogger(__name__)

NAME = "malpedia"
BASE = "https://malpedia.caad.fkie.fraunhofer.de"
API = f"{BASE}/api"
LIBRARY_URL = f"{BASE}/library/download"
ACTORS, FAMILIES, LIBRARY = "actors.json", "families.json", "library.bib"
PROGRESS_EVERY = 100
# A few actors failing is a problem with those actors, and they are skipped.
# More than this share failing means Malpedia itself is failing, and the last
# good snapshot is kept instead.
MAX_FAILED_SHARE = 0.05


def actor_id(value: str) -> str:
    """The Malpedia actor ID for a display name.

    The bulk /get/actors payload is keyed by display name and carries no ID.
    Malpedia's IDs are the name in lower case with spaces and slashes turned
    into underscores; on 2026-09-29 this rule reproduced all 1,056 IDs that
    /list/actors returned. fetch() still checks every derived ID against that
    list, so a change in the rule costs extra requests, not wrong IDs.
    """
    return value.strip().lower().replace(" ", "_").replace("/", "_")


def _labels(values) -> list[str]:
    """Trimmed, single-line, non-empty strings, deduplicated in source order.

    Malpedia gives some fields as a string and others as a list, and a few
    values carry stray whitespace. Published labels must be trimmed single
    lines, so every value passes through here.
    """
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for v in values:
        text = " ".join(v.split()) if isinstance(v, str) else ""
        if text and text not in out:
            out.append(text)
    return out


def _dump(data) -> bytes:
    # Sorted keys make two snapshots of unchanged data byte-identical, so a
    # diff between weeks shows only real changes.
    return json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _load(store: SnapshotStore, name: str):
    raw = store.latest(NAME, name)
    return None if raw is None else json.loads(raw.decode("utf-8-sig"))


# The BibTeX library ---------------------------------------------------------

_ENTRY_START = re.compile(r"^@(\w+)\{([^,\s]+),\s*$")
_FIELD = re.compile(r"^\s*([A-Za-z]+)\s*=\s*\{(.*)\},?\s*$")
# BibTeX escapes a few URL characters. Malpedia's export does not use them
# today, but an escaped underscore would otherwise break the URL join.
_LATEX_ESCAPE = re.compile(r"\\([_%&#$])")


def parse_bib(text: str) -> dict[str, dict[str, str]]:
    """Malpedia's BibTeX library as {entry key: {field: value}}.

    The parser reads one field per line, which is how Malpedia writes every
    entry. It keeps the entry key because families cite library entries by
    key, and it matches field names exactly, so `urldate` (when Malpedia saw
    the page) is never mistaken for `url` or `date`.
    """
    entries: dict[str, dict[str, str]] = {}
    current: dict[str, str] | None = None
    for line in text.splitlines():
        start = _ENTRY_START.match(line)
        if start:
            current = entries.setdefault(start.group(2), {})
            continue
        if current is None:
            continue
        if line.strip() == "}":
            current = None
            continue
        field = _FIELD.match(line)
        if field:
            value = field.group(2).strip()
            # Titles are double-braced to keep their capitalisation.
            if value.startswith("{") and value.endswith("}"):
                value = value[1:-1].strip()
            if field.group(1).lower() == "url":
                value = _LATEX_ESCAPE.sub(r"\1", value)
            current[field.group(1).lower()] = value
    return entries


def _library(store: SnapshotStore) -> dict[str, dict[str, str]]:
    raw = store.latest(NAME, LIBRARY)
    return {} if raw is None else parse_bib(raw.decode("utf-8-sig"))


def library_dates(store: SnapshotStore) -> dict[str, str]:
    """Map norm_url(url) to the YYYY-MM-DD publication date in Malpedia's library.

    An entry without a full date is skipped. That includes a bare year, which
    would put the report on 1 January and skew quarterly trends; the report
    falls through to its next date basis instead. When two entries share a
    URL, the earlier date wins, because a report cannot predate its first
    publication.
    """
    dates: dict[str, str] = {}
    for entry in _library(store).values():
        url, date = entry.get("url"), entry.get("date")
        if not url or not date or not re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", date):
            continue
        date = parse_date(date)
        if date is None:
            continue
        key = norm_url(url)
        dates[key] = min(date, dates.get(key, date))
    return dates


def report_links(store: SnapshotStore) -> dict[str, list[str]]:
    """Map norm_url(report url) to the sorted actor names Malpedia attributes it to.

    Each family lists report URLs directly (`urls`) and through library
    entries cited by BibTeX key (`library_entries`). Every one of those
    reports is linked to the family's `attribution` names. The names stay
    verbatim, because about 70 of them, such as "APT 29", are not any actor's
    display name, and the resolver, not this connector, decides which actor a
    name means. A family with no attribution links nothing.
    """
    families = _load(store, FAMILIES) or {}
    library = _library(store)
    links: dict[str, set[str]] = defaultdict(set)
    for family in families.values():
        if not isinstance(family, dict):
            continue
        names = _labels(family.get("attribution"))
        if not names:
            continue
        urls = list(family.get("urls") or [])
        for key in family.get("library_entries") or []:
            url = library.get(key, {}).get("url")
            if url:
                urls.append(url)
        for url in urls:
            if isinstance(url, str) and url.strip():
                links[norm_url(url)].update(names)
    return {url: sorted(names) for url, names in links.items()}


# The connector ---------------------------------------------------------------

def _is_actor(body) -> bool:
    return isinstance(body, dict) and bool(_labels(body.get("value")))


def _is_family(body) -> bool:
    # A handful of real families, such as win.idat_loader, have an empty
    # common_name, so the key must be present but its value may be blank.
    return isinstance(body, dict) and "common_name" in body


def _family_name(fid: str, family: dict) -> str:
    """The family's common_name, or a name made from its ID when that is blank.

    An ID such as win.idat_loader becomes "idat loader": the platform prefix
    goes and underscores become spaces, which is how the family is written in
    reports. The family is still malware the resolver must recognise, so it
    is named rather than dropped.
    """
    names = _labels(family.get("common_name"))
    return names[0] if names else " ".join(fid.split(".", 1)[-1].replace("_", " ").split()) or fid


class MalpediaConnector(Connector):
    name = NAME

    def fetch(self, store: SnapshotStore) -> None:
        """Save actors.json ({id: actor}), families.json ({id: family}) and library.bib.

        The two bulk endpoints replace roughly a thousand per-actor calls, which
        take about 20 minutes at one request per second. If either bulk payload
        is missing or has an unexpected shape, the connector falls back to one
        call per actor. A few actors that fail on their own are skipped. Nothing
        is saved until every payload has been fetched and checked, so a failure
        leaves the last good snapshot in place.
        """
        ids = http.get_json(f"{API}/list/actors")
        if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i for i in ids):
            raise ValueError("malpedia: /list/actors returned no actor IDs")
        try:
            actors, families = self._fetch_bulk(ids)
            bulk = True
        except (httpx.HTTPError, ValueError) as e:
            # json.JSONDecodeError is a ValueError, so a non-JSON body lands here too.
            log.warning("malpedia: bulk endpoints unusable (%s); fetching %d actors one by one", e, len(ids))
            actors, families, bulk = {}, {}, False

        # Listed actors the bulk payload lacks, or every actor after a
        # fallback, are fetched one by one.
        missing = [i for i in ids if i not in actors]
        failed = self._fetch_each(missing, actors, families)
        if len(failed) > len(ids) * MAX_FAILED_SHARE:
            raise ValueError(f"malpedia: {len(failed)} of {len(ids)} actors failed; snapshot not saved")
        if failed:
            log.warning("malpedia: skipped %d actors that failed: %s", len(failed), ", ".join(failed[:10]))
        if not bulk:
            # Per-actor calls return only families attributed to some actor, a
            # fraction of what the bulk endpoint lists. The others carry over
            # from the last snapshot, so the resolver can still type their
            # names as malware and the smaller payload does not trip the
            # shrink guard.
            previous = _load(store, FAMILIES) or {}
            carried = {k: v for k, v in previous.items() if k not in families and _is_family(v)}
            if carried:
                log.info("malpedia: kept %d families from the last snapshot", len(carried))
            families = {**carried, **families}

        library = http.get_text(LIBRARY_URL)
        if not parse_bib(library):
            raise ValueError("malpedia: the library download has no BibTeX entries")
        store.save(self.name, ACTORS, _dump(actors))
        store.save(self.name, FAMILIES, _dump(families))
        store.save(self.name, LIBRARY, library.encode("utf-8"))

    def _fetch_bulk(self, ids: list[str]) -> tuple[dict, dict]:
        raw_actors = http.get_json(f"{API}/get/actors")
        if not isinstance(raw_actors, dict):
            raise ValueError(f"/get/actors returned {type(raw_actors).__name__}, not a dict")
        raw_families = http.get_json(f"{API}/get/families")
        if not isinstance(raw_families, dict):
            raise ValueError(f"/get/families returned {type(raw_families).__name__}, not a dict")
        families = {k: v for k, v in raw_families.items() if _is_family(v)}
        if not families:
            raise ValueError("/get/families holds no usable family")
        dropped = len(raw_families) - len(families)
        if dropped:
            log.warning("malpedia: dropped %d bulk families that are not family objects", dropped)

        # /list/actors is the authority on IDs. A bulk actor whose derived ID
        # is not listed is dropped, and fetch() gets a listed ID the bulk
        # payload lacks on its own, so an actor never appears under two IDs.
        listed = set(ids)
        actors, unlisted = {}, []
        for body in raw_actors.values():
            if not _is_actor(body):
                continue
            key = actor_id(body["value"])
            if key in listed:
                actors[key] = body
            else:
                unlisted.append(body["value"])
        if not actors:
            raise ValueError("/get/actors holds no actor whose ID /list/actors knows")
        if unlisted:
            log.warning("malpedia: %d bulk actors have no listed ID and were dropped: %s",
                        len(unlisted), ", ".join(unlisted[:10]))
        return actors, families

    def _fetch_each(self, keys: list[str], actors: dict, families: dict) -> list[str]:
        """Fetch each actor on its own into `actors`, and return the keys that failed.

        One actor Malpedia cannot serve is skipped rather than failing the run.
        fetch() decides whether the number of failures means Malpedia itself
        is down.
        """
        if keys:
            log.info("malpedia: fetching %d actors one by one", len(keys))
        failed = []
        for n, key in enumerate(keys, 1):
            try:
                actors[key] = self._fetch_actor(key, families)
            except (httpx.HTTPError, ValueError) as e:
                failed.append(key)
                log.debug("malpedia: actor %s failed: %s", key, e)
            if n % PROGRESS_EVERY == 0:
                log.info("malpedia: %d of %d actors fetched", n, len(keys))
        return failed

    def _fetch_actor(self, key: str, families: dict) -> dict:
        """One actor, with its embedded family bodies moved into `families`.

        The actor keeps only the sorted family IDs, so actors.json has the same
        shape and roughly the same size whichever path fetched it. The
        embedded bodies match /get/family/<id>, so a family is fetched on its
        own only when its body is missing.
        """
        body = http.get_json(f"{API}/get/actor/{quote(key, safe='')}")
        if not _is_actor(body):
            raise ValueError(f"malpedia: /get/actor/{key} returned no actor")
        embedded = body.get("families") or {}
        for fid, family in embedded.items():
            if not _is_family(family):
                family = http.get_json(f"{API}/get/family/{quote(fid, safe='')}")
            if _is_family(family):
                families[fid] = family
        return {**body, "families": sorted(embedded)}

    def normalize(self, store: SnapshotStore) -> SourceBundle:
        actors = _load(store, ACTORS)
        if not actors:
            return SourceBundle(source=self.name)
        families = {k: v for k, v in (_load(store, FAMILIES) or {}).items() if _is_family(v)}
        # The records are only as fresh as the snapshot. After a failed fetch
        # that snapshot is older than today, and the date must say so.
        retrieved_at = store.latest_date(self.name)

        # Malpedia links a family to an actor when the family's attribution
        # holds the actor's exact display name. The bulk path has only that
        # link; the per-actor path also records the family IDs it was given.
        attributed: dict[str, set[str]] = defaultdict(set)
        for fid, family in families.items():
            for name in _labels(family.get("attribution")):
                attributed[name].add(fid)

        records: list[ActorRecord] = []
        dropped = 0
        for key, body in sorted(actors.items()):
            if not _is_actor(body):
                dropped += 1
                continue
            name = _labels(body["value"])[0]
            meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
            fids = set(body.get("families") or []) | attributed.get(name, set())
            malware = sorted({_family_name(f, families[f]) for f in fids if f in families})
            records.append(ActorRecord(
                source=self.name,
                source_id=key,
                name=name,
                aliases=[a for a in _labels(meta.get("synonyms")) if a != name],
                # Country is an ISO 3166-1 alpha-2 code, as in MISP.
                origin=[c.upper() for c in _labels(meta.get("country"))],
                # The cfr-* fields in Malpedia's records copy the Council on
                # Foreign Relations tracker, whose terms bar public reuse, so
                # they are never read.
                motivation=_labels(meta.get("motive")),
                targets_countries=_labels(meta.get("suspected-victims")),
                targets_sectors=_labels(meta.get("targeted-sector")),
                malware=malware,
                retrieved_at=retrieved_at,
            ))

        software = []
        for fid, family in sorted(families.items()):
            name = _family_name(fid, family)
            software.append(SoftwareRecord(
                source=self.name,
                source_id=fid,
                name=name,
                aliases=[a for a in _labels(family.get("alt_names")) if a != name],
                # Malpedia inventories malware; it has no separate tool category.
                kind="malware",
                attribution=_labels(family.get("attribution")),
                retrieved_at=retrieved_at,
            ))
        if dropped:
            # Malformed records are dropped one by one and counted, never
            # silently, so a change in the payload shows up in the build log.
            log.warning("malpedia: dropped %d actors without a display name", dropped)
        return SourceBundle(source=self.name, actors=records, software=software)
