"""Microsoft's threat actor naming table: its actor names, other names and origin.

Microsoft Threat Intelligence publishes one table that maps its own actor names
(Forest Blizzard, Midnight Blizzard) to the names other vendors use. The repository
is licensed CC BY 4.0, so every field taken here may be published with credit. The
licence grants no right to Microsoft's names or logos as trademarks, and the
site does not imply that Microsoft endorses it.

The table's "Origin/Threat" column mixes two things: a country, and a label for
the kind of actor ("Financially motivated", "Influence operations"). Only the
country is an origin claim, so the labels are left out.
"""
import json
import logging

from aptx.core import http
from aptx.core.models import ActorRecord, SourceBundle
from aptx.core.snapshot import SnapshotStore
from aptx.sources.base import Connector

log = logging.getLogger(__name__)

NAME = "microsoft"
FILE = "MicrosoftMapping.json"
URL = "https://raw.githubusercontent.com/microsoft/mstic/master/PublicFeeds/ThreatActorNaming/MicrosoftMapping.json"

# What the Origin/Threat column says about an actor besides where it is from.
# These are not countries, so they would only ever be dropped as unknown origins.
_KINDS = frozenset({
    "financially motivated", "influence operations", "private sector offensive actor",
    "group in development", "covert network",
})


def _tidy(text) -> str:
    return " ".join(text.split()) if isinstance(text, str) else ""


def _rows(payload: bytes) -> list[dict]:
    """The table's rows, or ValueError when it holds none.

    A 200 response can still carry an error page or an empty list. Such a
    payload must never become the newest snapshot, because the source would
    then look fresh while publishing nothing.
    """
    data = json.loads(payload.decode("utf-8-sig"))
    if not isinstance(data, list) or not any(isinstance(r, dict) and r.get("Threat actor name") for r in data):
        raise ValueError(f"{NAME}: the table holds no actors; keeping the last snapshot")
    return data


def _origin(text) -> list[str]:
    parts = (_tidy(p) for p in str(text or "").split(","))
    return [p for p in parts if p and p.casefold() not in _KINDS]


def _aliases(text, name: str) -> list[str]:
    seen = {name.casefold()}
    out = []
    for part in str(text or "").split(","):
        alias = _tidy(part)
        if alias and alias.casefold() not in seen:
            seen.add(alias.casefold())
            out.append(alias)
    return out


class MicrosoftConnector(Connector):
    name = NAME

    def fetch(self, store: SnapshotStore) -> None:
        payload = http.get_bytes(URL)
        _rows(payload)
        store.save(NAME, FILE, payload)

    def normalize(self, store: SnapshotStore) -> SourceBundle:
        raw = store.latest(NAME, FILE)
        if raw is None:
            log.warning("%s: no snapshot to normalize; returning an empty bundle", NAME)
            return SourceBundle(source=NAME)
        # The snapshot's date, not today's: after a failed fetch this reads an
        # older snapshot, and stale data must not claim to be fresh.
        retrieved = store.latest_date(NAME)

        bundle = SourceBundle(source=NAME)
        seen: set[str] = set()
        dropped = 0
        for row in _rows(raw):
            name = _tidy(row.get("Threat actor name")) if isinstance(row, dict) else ""
            # The table names each actor once, and the name is the only handle it gives.
            if not name or name.casefold() in seen:
                dropped += 1
                continue
            seen.add(name.casefold())
            bundle.actors.append(ActorRecord(
                source=NAME,
                source_id=name,
                name=name,
                aliases=_aliases(row.get("Other names"), name),
                origin=_origin(row.get("Origin/Threat")),
                retrieved_at=retrieved))
        if dropped:
            log.warning("%s: dropped %d rows without a usable name", NAME, dropped)
        bundle.actors.sort(key=lambda a: a.source_id)
        return bundle
