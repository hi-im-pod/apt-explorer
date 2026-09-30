"""MISP galaxy threat-actor cluster: actors, synonyms, origin, motive, sectors.

MISP has the widest synonym lists of any source here, which makes it the main
bridge between vendor names. It is CC0, so every field taken from it may be
published, with one exclusion: the cfr-* fields cite the Council on Foreign
Relations Cyber Operations Tracker, whose terms bar public reuse, so no
connector reads them.
"""
import json
import logging

from aptx.core import http
from aptx.core.models import ActorRecord, SourceBundle
from aptx.core.snapshot import SnapshotStore
from aptx.sources.base import Connector

log = logging.getLogger(__name__)

NAME = "misp"
FILE = "threat-actor.json"
URL = "https://raw.githubusercontent.com/MISP/misp-galaxy/main/clusters/threat-actor.json"

# Values that say the galaxy does not know. Kept, they would read as a claim,
# for example an origin called "Unknown" in conflict with a real one.
_PLACEHOLDERS = frozenset({"unknown", "[unknown]"})


def _as_list(value) -> list:
    # A meta field holds a string when the galaxy has one value and a list
    # when it has several. Wrapping lets every field be read the same way.
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _labels(values: list, exclude: str | None = None) -> list[str]:
    """Trimmed, non-empty labels without repeats, in the galaxy's own order."""
    seen = {exclude} if exclude else set()
    out = []
    for v in values:
        if not isinstance(v, str):
            continue
        v = " ".join(v.split())
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _names(meta: dict, key: str, exclude: str) -> list[str]:
    # The galaxy often lists an actor's own name among its synonyms. The name
    # is already the record's name, so it is left out of the aliases.
    return _labels(_as_list(meta.get(key)), exclude)


def _values(meta: dict, *keys: str) -> list[str]:
    values = _labels([x for k in keys for x in _as_list(meta.get(k))])
    return [v for v in values if v.casefold() not in _PLACEHOLDERS]


def _check_cluster(payload: bytes) -> None:
    # The snapshot store refuses a payload that shrank against the last one.
    # On a first run there is no last one, so an empty cluster has to be
    # refused on its content instead.
    data = json.loads(payload)
    if not isinstance(data, dict) or not data.get("values"):
        raise ValueError(f"{NAME}: the cluster holds no values; keeping the last snapshot")


class MispConnector(Connector):
    name = NAME

    def fetch(self, store: SnapshotStore) -> None:
        payload = http.get_bytes(URL)
        _check_cluster(payload)
        store.save(NAME, FILE, payload)

    def normalize(self, store: SnapshotStore) -> SourceBundle:
        raw = store.latest(NAME, FILE)
        if raw is None:
            log.warning("%s: no snapshot to normalize; returning an empty bundle", NAME)
            return SourceBundle(source=NAME)
        # The snapshot's date, not today's. After a failed fetch this reads an
        # older snapshot, and stale data must not claim to be fresh.
        retrieved = store.latest_date(NAME)

        bundle = SourceBundle(source=NAME)
        dropped = 0
        for v in json.loads(raw).get("values") or []:
            value = v.get("value")
            name = " ".join(value.split()) if isinstance(value, str) else ""
            if not name:
                dropped += 1
                continue
            meta = v.get("meta") or {}
            bundle.actors.append(ActorRecord(
                source=NAME,
                # Every galaxy entry carries a uuid. Should one ever lack it,
                # the name is the only stable handle left, because the galaxy
                # keeps its names unique.
                source_id=(v.get("uuid") or name).strip(),
                name=name,
                aliases=_names(meta, "synonyms", name),
                origin=_values(meta, "country"),
                motivation=_values(meta, "motive"),
                targets_sectors=_values(meta, "targeted-sector"),
                retrieved_at=retrieved))
        if dropped:
            log.warning("%s: dropped %d entries without a name", NAME, dropped)
        bundle.actors.sort(key=lambda a: a.source_id)
        return bundle
