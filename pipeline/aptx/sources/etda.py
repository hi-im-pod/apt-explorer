"""ETDA Threat Group Cards: actor names, origin, motivation and observed targets.

ETDA is licensed CC BY-NC-SA 4.0, and SOURCES.md sets it to derived-only. Only
short values are taken: names, countries, sectors, motivation and the
first-seen year. A card's description, information links and operation text
never enter a record, so they cannot reach data/ by any later mistake.
"""
import json
import logging
import re

from aptx.core import http
from aptx.core.dates import parse_date
from aptx.core.models import ActorRecord, SourceBundle
from aptx.core.snapshot import SnapshotStore
from aptx.sources.base import Connector, publish_policy

log = logging.getLogger(__name__)

NAME = "etda"
FILE = "threat-group-cards.json"
URL = "https://apt.etda.or.th/cgi-bin/getcard.cgi?g=all&o=j"

# The licence string the audit read in the JSON on 2026-09-29. SOURCES.md's
# publish value was decided for this licence only.
AUDITED_LICENCE = "Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License"

# Values that say the card does not know. Kept, they would read as claims:
# "[Unknown]" as an origin, or "others" as a target country.
_PLACEHOLDERS = frozenset({"[unknown]", "unknown", "others"})
# ETDA writes first-seen as a year, sometimes as "~2019". Only a plain year
# or ISO date is kept, so no approximate wording reaches a date field.
_FIRST_SEEN = re.compile(r"(19|20)\d{2}(-\d{2}){0,2}")


def _labels(values, exclude: str | None = None) -> list[str]:
    """Trimmed, non-empty labels without repeats, in the card's own order."""
    seen = {exclude} if exclude else set()
    out = []
    for v in values or []:
        if not isinstance(v, str):
            continue
        v = " ".join(v.split())
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _values(card: dict, key: str) -> list[str]:
    value = card.get(key)
    values = _labels(value if isinstance(value, list) else [value])
    return [v for v in values if v.casefold() not in _PLACEHOLDERS]


def _first_seen(card: dict) -> list[str]:
    value = card.get("first-seen")
    value = value.strip() if isinstance(value, str) else ""
    return [value] if _FIRST_SEEN.fullmatch(value) else []


def _card_names(card: dict) -> list[str]:
    # The "actor" field joins a card's names into one display string, such as
    # "Anchor Panda, APT 14", which no other source would ever match. The
    # names list holds the same names one by one, the primary name first.
    names = _labels([n.get("name") for n in card.get("names") or [] if isinstance(n, dict)])
    if not names and isinstance(card.get("actor"), str):
        names = _labels(card["actor"].split(","))
    return names


def _load(store: SnapshotStore) -> dict | None:
    raw = store.latest(NAME, FILE)
    return None if raw is None else json.loads(raw)


def _check_cards(payload: bytes) -> None:
    # The snapshot store refuses a payload that shrank against the last one.
    # On a first run there is no last one, so an empty file has to be refused
    # on its content instead.
    data = json.loads(payload)
    if not isinstance(data, dict) or not data.get("values"):
        raise ValueError(f"{NAME}: the file holds no cards; keeping the last snapshot")


def last_db_change(store: SnapshotStore) -> str | None:
    """The date ETDA last changed its database, as YYYY-MM-DD.

    The fetch keeps succeeding while the database itself stands still, so
    source health needs this date, not the fetch date, to show how old ETDA's
    data is.
    """
    data = _load(store)
    return parse_date(data.get("last-db-change")) if isinstance(data, dict) else None


class EtdaConnector(Connector):
    name = NAME

    def fetch(self, store: SnapshotStore) -> None:
        payload = http.get_bytes(URL)
        _check_cards(payload)
        store.save(NAME, FILE, payload)

    def policy(self, store: SnapshotStore, sources_md=None) -> str:
        """The publish value for ETDA, after a licence drift check.

        SOURCES.md's value holds only while the snapshot still carries the
        licence the audit read. If ETDA changes or drops its licence string,
        ETDA returns to evidence-only until a person reads the terms again.
        Use this instead of publish_policy("etda"), which skips the check.
        """
        data = _load(store)
        found = data.get("license") if isinstance(data, dict) else None
        if not isinstance(found, str) or " ".join(found.split()) != AUDITED_LICENCE:
            log.warning("%s: licence %r is not the audited %r; using evidence-only until "
                        "SOURCES.md is re-audited", NAME, found, AUDITED_LICENCE)
            return "evidence-only"
        return publish_policy(NAME, sources_md)

    def normalize(self, store: SnapshotStore) -> SourceBundle:
        data = _load(store)
        if data is None:
            log.warning("%s: no snapshot to normalize; returning an empty bundle", NAME)
            return SourceBundle(source=NAME)
        # The snapshot's date, not today's. After a failed fetch this reads an
        # older snapshot, and stale data must not claim to be fresh.
        retrieved = store.latest_date(NAME)

        bundle = SourceBundle(source=NAME)
        dropped = 0
        for card in data.get("values") or []:
            names = _card_names(card)
            if not names:
                dropped += 1
                continue
            name = names[0]
            # Each field is listed on purpose, never copied in bulk. The
            # sponsor field is left out because it is prose, often quoting a
            # vendor, where the data contract expects a state name. The tools
            # list is left out because it mixes malware names with phrases
            # such as "Living off the Land".
            bundle.actors.append(ActorRecord(
                source=NAME,
                # A card without a uuid keeps its primary name as the handle,
                # which ETDA keeps unique across cards.
                source_id=(card.get("uuid") or name).strip(),
                name=name,
                # The names are already free of repeats, so the rest are aliases.
                aliases=names[1:],
                origin=_values(card, "country"),
                motivation=_values(card, "motivation"),
                targets_countries=_values(card, "observed-countries"),
                targets_sectors=_values(card, "observed-sectors"),
                first_seen=_first_seen(card),
                retrieved_at=retrieved))
        if dropped:
            log.warning("%s: dropped %d cards without a name", NAME, dropped)
        bundle.actors.sort(key=lambda a: a.source_id)
        return bundle
