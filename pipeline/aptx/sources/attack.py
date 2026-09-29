"""MITRE ATT&CK® enterprise STIX: groups, campaigns and software.

ATT&CK is the reference the other sources are matched against. Its group IDs
become actor IDs on the site, its campaigns become campaign pages, and its
software entries let the resolver recognise a name as malware or a tool rather
than an actor.
"""
import json
import logging
import re
from collections import defaultdict

from aptx.core import http
from aptx.core.dates import parse_date
from aptx.core.models import ActorRecord, CampaignRecord, SoftwareRecord, SourceBundle
from aptx.core.snapshot import SnapshotStore

log = logging.getLogger(__name__)

NAME = "attack"
BUNDLE = "enterprise-attack.json"
LICENCE = "LICENSE.txt"
_REPO = "https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master"
BUNDLE_URL = f"{_REPO}/enterprise-attack/enterprise-attack.json"
LICENCE_URL = f"{_REPO}/LICENSE.txt"

# The object types that become records. Only these count as dropped when they
# lack an ATT&CK ID, so collections and relationships never inflate the count.
_MAPPED = frozenset({"intrusion-set", "campaign", "malware", "tool"})
_DESIGNATION = re.compile(r"©\s*(\d{4})\s+The MITRE Corporation")


def _live(obj: dict) -> bool:
    # A revoked object was replaced by another, and a deprecated one is no
    # longer maintained. ATT&CK no longer asserts either, so neither they nor
    # the links that touch them may reach the data.
    return not obj.get("revoked") and not obj.get("x_mitre_deprecated")


def _attack_id(obj: dict) -> str | None:
    for ref in obj.get("external_references") or []:
        if ref.get("source_name") == "mitre-attack" and ref.get("external_id"):
            return ref["external_id"].strip()
    return None


def _ref_urls(obj: dict) -> list[str]:
    # The mitre-attack reference points at ATT&CK's own page for the object.
    # Only the other references cite reports, which is what these URLs are for.
    return [ref["url"].strip() for ref in obj.get("external_references") or []
            if ref.get("url") and ref.get("source_name") != "mitre-attack"]


def _labels(values, exclude: str | None = None) -> list[str]:
    """Trimmed, non-empty labels without repeats, in the source's own order.

    Sources often list the record's own name among its aliases. The name is
    already the record's name, so it is left out here.
    """
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


def _load(store: SnapshotStore) -> tuple[dict[str, dict], list[dict]] | None:
    """Live objects by STIX ID, and the live relationships between them."""
    raw = store.latest(NAME, BUNDLE)
    if raw is None:
        return None
    objects = json.loads(raw).get("objects") or []
    live = {o["id"]: o for o in objects
            if o.get("type") != "relationship" and o.get("id") and _live(o)}
    rels = [o for o in objects
            if o.get("type") == "relationship" and _live(o)
            and o.get("source_ref") in live and o.get("target_ref") in live]
    return live, rels


def _check_bundle(payload: bytes) -> None:
    # The snapshot store refuses a payload that shrank against the last one.
    # On a first run there is no last one, so an empty bundle has to be
    # refused on its content instead.
    data = json.loads(payload)
    objects = data.get("objects") if isinstance(data, dict) else None
    if not objects or not any(isinstance(o, dict) and o.get("type") == "intrusion-set" for o in objects):
        raise ValueError(f"{NAME}: the bundle holds no intrusion sets; keeping the last snapshot")


class AttackConnector:
    name = NAME

    def fetch(self, store: SnapshotStore) -> None:
        # Both files are downloaded and the bundle checked before anything is
        # saved. The licence is saved last: were it saved alone, its new dated
        # folder would make an old bundle look fresh.
        bundle = http.get_bytes(BUNDLE_URL)
        licence = http.get_bytes(LICENCE_URL)
        _check_bundle(bundle)
        store.save(NAME, BUNDLE, bundle)
        store.save(NAME, LICENCE, licence)

    def normalize(self, store: SnapshotStore) -> SourceBundle:
        loaded = _load(store)
        if loaded is None:
            log.warning("%s: no snapshot to normalize; returning an empty bundle", NAME)
            return SourceBundle(source=NAME)
        live, rels = loaded
        # The snapshot's date, not today's. After a failed fetch this reads an
        # older snapshot, and stale data must not claim to be fresh.
        retrieved = store.latest_date(NAME)

        ids: dict[str, str] = {}
        dropped = 0
        for sid, o in live.items():
            aid = _attack_id(o)
            if o.get("type") in _MAPPED and not (aid and (o.get("name") or "").strip()):
                dropped += 1
            elif aid:
                ids[sid] = aid
        if dropped:
            # Every ATT&CK record should carry an ID. Dropping is right, but it
            # is logged so a change in the bundle's shape does not go unseen.
            log.warning("%s: dropped %d objects without an ATT&CK ID or name", NAME, dropped)

        techniques: dict[str, set[str]] = defaultdict(set)
        malware: dict[str, set[str]] = defaultdict(set)
        actor_refs: dict[str, set[str]] = defaultdict(set)
        campaign_urls: dict[str, set[str]] = defaultdict(set)
        for r in rels:
            src, tgt = live[r["source_ref"]], live[r["target_ref"]]
            if src["id"] not in ids or tgt["id"] not in ids:
                continue
            kind, st, tt = r.get("relationship_type"), src.get("type"), tgt.get("type")
            if kind == "uses" and tt == "attack-pattern" and st in ("intrusion-set", "campaign"):
                techniques[src["id"]].add(ids[tgt["id"]])
            elif kind == "uses" and tt in ("malware", "tool") and st == "intrusion-set":
                malware[src["id"]].add(tgt["name"].strip())
            elif kind == "attributed-to" and st == "campaign" and tt == "intrusion-set":
                actor_refs[src["id"]].add(ids[tgt["id"]])
            if st == "campaign":
                # A campaign's reports are cited on its links as well as on the
                # campaign itself.
                campaign_urls[src["id"]].update(_ref_urls(r))

        bundle = SourceBundle(source=NAME)
        for sid, o in live.items():
            if sid not in ids:
                continue
            aid, t, name = ids[sid], o.get("type"), o["name"].strip()
            if t == "intrusion-set":
                bundle.actors.append(ActorRecord(
                    source=NAME, source_id=aid, name=name,
                    aliases=_labels(o.get("aliases"), name),
                    techniques=sorted(techniques[sid]), malware=sorted(malware[sid]),
                    retrieved_at=retrieved))
            elif t == "campaign":
                bundle.campaigns.append(CampaignRecord(
                    source=NAME, source_id=aid, name=name,
                    first_seen=parse_date(o.get("first_seen")), last_seen=parse_date(o.get("last_seen")),
                    actor_refs=sorted(actor_refs[sid]), techniques=sorted(techniques[sid]),
                    report_urls=sorted(set(_ref_urls(o)) | campaign_urls[sid]),
                    retrieved_at=retrieved))
            elif t in ("malware", "tool"):
                bundle.software.append(SoftwareRecord(
                    source=NAME, source_id=aid, name=name,
                    aliases=_labels(o.get("x_mitre_aliases"), name), kind=t,
                    retrieved_at=retrieved))
        # Sorted by ID so a weekly rebuild with no real change gives no diff.
        for records in (bundle.actors, bundle.campaigns, bundle.software):
            records.sort(key=lambda rec: rec.source_id)
        return bundle


def group_reference_urls(store: SnapshotStore) -> dict[str, list[str]]:
    """Report URLs that ATT&CK cites for each group, keyed by group ID.

    These citations are one of the publishable ways to link a report to an
    actor. They come from the group itself and from its live relationships,
    including campaigns attributed to it. A citation on a revoked link, or on a
    link to a revoked object, is left out along with the link.
    """
    loaded = _load(store)
    if loaded is None:
        return {}
    live, rels = loaded
    groups = {sid: aid for sid, o in live.items()
              if o.get("type") == "intrusion-set" and (aid := _attack_id(o))}
    urls: dict[str, set[str]] = defaultdict(set)
    for sid, aid in groups.items():
        urls[aid].update(_ref_urls(live[sid]))
    for r in rels:
        for end in (r["source_ref"], r["target_ref"]):
            if end in groups:
                urls[groups[end]].update(_ref_urls(r))
    return {aid: sorted(u) for aid, u in sorted(urls.items()) if u}


def copyright_year(store: SnapshotStore) -> str | None:
    """The year in MITRE's copyright designation, from the saved LICENSE.txt.

    The notice shipped with data/ must reproduce MITRE's designation exactly,
    and its year changes when MITRE updates the file. None means the licence
    is missing or no longer holds a designation in the expected form, which
    needs a person to read the licence again.
    """
    raw = store.latest(NAME, LICENCE)
    if raw is None:
        return None
    m = _DESIGNATION.search(raw.decode("utf-8", errors="replace"))
    return m.group(1) if m else None
