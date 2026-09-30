"""Merge actor records from every source into one actor per real-world group.

Two records are candidates for a merge when they share a name key (see
names.norm). Each shared key is kept as evidence, so every merge can be traced
to the aliases that caused it. A key that would put two ATT&CK groups into one
actor is refused and recorded as an ambiguity instead, because ATT&CK already
decided those are different groups and an alias shared between them says
nothing about which one another source meant. Looking such a key up still
finds the one ATT&CK group that carries it directly, if there is exactly one.

The registry uses every record it is given as merge evidence, whatever that
source's publish policy is. Which facts reach data/ is decided at assembly, so
nothing here reads the licence gate.
"""
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from aptx.build import slugs
from aptx.core.models import ActorRecord, Claim, Provenance, SoftwareRecord
from aptx.resolve.names import norm

# Only a record that ATT&CK itself published under a group ID counts as an
# ATT&CK group. Its bare ID becomes the actor ID, file name and URL segment, so
# it must fit the contract's G[0-9]{4} form; any other ATT&CK record is treated
# like a record from any other source.
_ATTACK_GROUP = re.compile(r"G[0-9]{4}")

# (alias key, node ID, node ID): the key two records shared, and the records it
# joined. A node ID is the ATT&CK group ID, or "source:source_id" otherwise.
Evidence = tuple[str, str, str]


@dataclass
class ResolvedActor:
    id: str
    name: str
    members: list[ActorRecord]
    aliases: list[Claim[str]]
    evidence: list[Evidence]


@dataclass
class Registry:
    actors: list[ResolvedActor]
    ambiguities: list[dict]
    _actor_ids: dict[str, str] = field(repr=False)
    _non_actor: dict[str, str] = field(repr=False)
    _source_record_count: int = field(repr=False)
    # The registry to publish as data/slugs.json, and which sources it was allowed to see. See resolve().
    slug_entries: list[dict] = field(default_factory=list, repr=False)
    shown_sources: frozenset[str] | None = None

    def lookup(self, name: str) -> str | None:
        """The actor ID a name resolves to.

        None when the name is unknown or has no key. It is also None when the
        name is ambiguous and no single ATT&CK group carries it directly:
        with two such groups, or with none, the registry cannot tell which
        group a report meant. When exactly one ATT&CK group carries the name as
        its own name or alias, the name resolves to that group even though the
        merge on it was refused and the ambiguity is on record.
        """
        return self._actor_ids.get(norm(name))

    def non_actor(self, name: str) -> str | None:
        """"malware" or "tool" when the name belongs to software and to no actor."""
        return self._non_actor.get(norm(name))

    def stats(self) -> dict:
        """Counts for data/resolution.json. The keys are fixed by the contract."""
        record_count = self._source_record_count
        return {
            "source_record_count": record_count,
            "actor_count": len(self.actors),
            "merge_count": record_count - len(self.actors),
            "evidence_edge_count": sum(len(a.evidence) for a in self.actors),
            "ambiguity_count": len(self.ambiguities),
            "non_actor_name_count": len(self._non_actor),
        }


def resolve(actors: list[ActorRecord], software: list[SoftwareRecord], *,
            previous_slugs: Iterable[Mapping] | None = None, shown_sources: Iterable[str] | None = None,
            build_date: str | None = None) -> Registry:
    """Merge actor records across sources and type software names.

    The result does not depend on the order of either list: every choice below
    is made in a sorted order, so a weekly rebuild from the same sources gives
    the same actors and IDs.

    Actor IDs are frozen slugs (see aptx.build.slugs). `previous_slugs` is the
    entries of the registry the last build wrote, or None for a first build.
    `shown_sources` is the sources whose actor facts a page may show, from
    slugs.shown_sources(policies); a slug is derived from the name that page
    displays, so it may only read members from those sources. None means every
    source is shown, which is right for tests and for a build with no
    evidence-only source. `build_date` is recorded as first_published for each
    new slug.
    """
    records: dict[str, list[ActorRecord]] = defaultdict(list)
    for record in actors:
        records[_node_id(record)].append(record)

    # Which nodes carry each key, and for how many of them it is a primary
    # name rather than only an alias.
    carriers: dict[str, set[str]] = defaultdict(set)
    named_by: dict[str, set[str]] = defaultdict(set)
    for node, recs in records.items():
        for record in recs:
            for value in _names(record):
                carriers[norm(value)].add(node)
            primary = norm(record.name)
            if primary:
                named_by[primary].add(node)

    groups = _Components(records)
    ambiguous: dict[str, list[str]] = {}
    edges: list[Evidence] = []
    for key in sorted((k for k, nodes in carriers.items() if len(nodes) > 1),
                      key=lambda k: _merge_priority(k, carriers[k], named_by[k])):
        nodes = sorted(carriers[key])
        attack_ids = groups.attack_ids(nodes)
        if len(attack_ids) > 1:
            ambiguous[key] = sorted(attack_ids)
            continue
        # A star from the smallest node records each shared key once per
        # record it joined, which is enough to trace every merge back to it.
        hub = nodes[0]
        for other in nodes[1:]:
            edges.append((key, hub, other))
            groups.union(hub, other)

    components = groups.components()
    shown = None if shown_sources is None else frozenset(shown_sources)
    ids, slug_entries = _assign_ids(components, records, list(previous_slugs or ()), shown,
                                    build_date or slugs.today())
    evidence: dict[str, list[Evidence]] = defaultdict(list)
    for edge in edges:
        evidence[groups.find(edge[1])].append(edge)

    resolved = []
    for root, nodes in components.items():
        members = sorted((r for n in nodes for r in records[n]),
                         key=lambda r: (_node_id(r), r.model_dump_json()))
        resolved.append(ResolvedActor(
            id=ids[root],
            name=_display_name(members),
            members=members,
            aliases=[_claim(value, r) for r in members for value in _names(r)],
            evidence=sorted(evidence[root]),
        ))
    resolved.sort(key=lambda a: a.id)

    actor_ids = {key: ids[groups.find(next(iter(nodes)))]
                 for key, nodes in carriers.items() if key not in ambiguous}
    # A refused key is still a name a report can use. When exactly one ATT&CK
    # group carries it itself, as its name or one of its own aliases, that
    # group is the only candidate ATT&CK's own data supports, so a report
    # tagged with the key resolves to it. The ambiguity stays on record, and
    # nothing is merged, so records from other sources that share only this key
    # still sit apart. With two direct carriers there is no way to choose.
    for key in ambiguous:
        direct = [n for n in carriers[key] if _is_attack_group(n)]
        if len(direct) == 1:
            actor_ids[key] = ids[groups.find(direct[0])]
    return Registry(
        actors=resolved,
        ambiguities=[{"alias": key, "candidates": ambiguous[key]} for key in sorted(ambiguous)],
        _actor_ids=actor_ids,
        _non_actor=_type_software(software, actor_keys=set(carriers)),
        _source_record_count=len(actors),
        slug_entries=slug_entries,
        shown_sources=shown,
    )


def _node_id(record: ActorRecord) -> str:
    """The merge node a record belongs to.

    Records from ATT&CK that share a group ID are one node from the start, so
    two copies of a group can never be split apart or flagged against each
    other.
    """
    if record.source == "attack" and _ATTACK_GROUP.fullmatch(record.source_id):
        return record.source_id
    return f"{record.source}:{record.source_id}"


def _is_attack_group(node: str) -> bool:
    # Every other node ID contains a colon, so only bare ATT&CK IDs match.
    return _ATTACK_GROUP.fullmatch(node) is not None


def _names(record: ActorRecord) -> list[str]:
    """The record's name and then its aliases, each once, with whitespace tidied.

    Values with no letters or digits are dropped. Their key would be empty, so
    they could only merge unrelated actors, and they are not names a reader
    could use.
    """
    seen: dict[str, None] = {}
    for value in (record.name, *record.aliases):
        value = " ".join(value.split())
        if norm(value):
            seen.setdefault(value)
    return list(seen)


def _merge_priority(key: str, nodes: set[str], named_by: set[str]) -> tuple:
    """The order in which shared keys are applied; stronger evidence comes first.

    When records chain two ATT&CK groups together, the keys applied first win,
    and the key that would close the chain is the one refused as ambiguous. A
    key an ATT&CK record carries itself is the most direct evidence, so it goes
    first. Among those, a key that is the primary name of two records outranks
    one that is only a name on one side, which outranks a shared alias; sources
    such as ETDA list loosely related groups as aliases. The key itself breaks
    ties so the result is fixed.
    """
    direct = any(_is_attack_group(n) for n in nodes)
    return (not direct, -min(len(named_by & nodes), 2), key)


class _Components:
    """Union-find over merge nodes that tracks the ATT&CK groups in each set."""

    def __init__(self, nodes: Iterable[str]):
        self._parent = {n: n for n in nodes}
        self._attack = {n: {n} if _is_attack_group(n) else set() for n in self._parent}

    def find(self, node: str) -> str:
        root = node
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[node] != root:
            self._parent[node], node = root, self._parent[node]
        return root

    def attack_ids(self, nodes: Iterable[str]) -> set[str]:
        """The ATT&CK groups already in the sets these nodes belong to."""
        return set().union(*(self._attack[self.find(n)] for n in nodes))

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra
            self._attack[ra] |= self._attack.pop(rb)

    def components(self) -> dict[str, list[str]]:
        """Each set's root mapped to its nodes, sorted."""
        out: dict[str, list[str]] = defaultdict(list)
        for node in sorted(self._parent):
            out[self.find(node)].append(node)
        return dict(out)


def _ranked_names(records: list[ActorRecord]) -> list[str]:
    """Every name the records use, the most common first.

    Spellings are counted together under their key, so "APT 28" and "APT28"
    add up to one name. A key that records use as their primary name ranks
    above one they list only as an alias. Within a key, the spelling used most
    often as a primary name comes first.
    """
    as_name: Counter[str] = Counter()
    carried: Counter[str] = Counter()
    spellings: dict[str, Counter[str]] = defaultdict(Counter)
    spellings_as_name: Counter[str] = Counter()
    for record in records:
        values = _names(record)
        for value in values:
            spellings[norm(value)][value] += 1
        carried.update({norm(v) for v in values})
        primary = " ".join(record.name.split())
        if norm(primary):
            as_name[norm(primary)] += 1
            spellings_as_name[primary] += 1
    keys = sorted(carried, key=lambda k: (-as_name[k], -carried[k], k))
    return [v for k in keys
            for v in sorted(spellings[k], key=lambda v: (-spellings_as_name[v], -spellings[k][v], v))]


def _display_name(members: list[ActorRecord]) -> str:
    """ATT&CK's name for the group when ATT&CK tracks it, else the most common name."""
    attack = [m for m in members if _is_attack_group(_node_id(m))]
    ranked = _ranked_names(attack) or _ranked_names(members)
    if ranked:
        return ranked[0]
    # No member has a usable name, only values such as "???". Show what the
    # source wrote rather than nothing.
    return next((" ".join(m.name.split()) for m in members if m.name.strip()), _node_id(members[0]))


def _claim(value: str, record: ActorRecord) -> Claim[str]:
    return Claim[str](value=value, prov=Provenance(
        source=record.source, source_id=record.source_id, retrieved_at=record.retrieved_at))


def _assign_ids(components: dict[str, list[str]], records: dict[str, list[ActorRecord]],
                previous: list[Mapping], shown: frozenset[str] | None, build_date: str) -> tuple[dict[str, str], list[dict]]:
    """The actor ID for each component, and the slug registry entries.

    An actor ATT&CK tracks keeps its group ID. Any other actor that has a
    published member gets a frozen slug from aptx.build.slugs, which reads only
    the members a page may show. An actor with nothing publishable never gets a
    page, so its ID is a hash, and it stays out of the registry.
    """
    ids: dict[str, str] = {}
    candidates: list[slugs.Candidate] = []
    for root, nodes in components.items():
        attack = next((n for n in nodes if _is_attack_group(n)), None)
        visible = [r for n in nodes for r in records[n] if shown is None or r.source in shown]
        if not visible:
            ids[root] = attack or slugs.hidden_id(nodes[0])
            continue
        candidates.append(slugs.Candidate(
            key=root, name=_display_name(visible), attack_id=attack,
            anchors=tuple(sorted({_node_id(r) for r in visible}))))
    assigned, entries = slugs.assign(candidates, previous, build_date)
    ids.update(assigned)
    return ids, entries


def _type_software(software: list[SoftwareRecord], actor_keys: set[str]) -> dict[str, str]:
    """Software name keys mapped to "malware" or "tool".

    A key that any actor record carries is left out, even when the actor is
    ambiguous: Winnti is both a malware family and a group name, and the
    registry must not hide the group. When sources disagree on the kind,
    ATT&CK wins, because it separates tools (often legitimate software that
    attackers reuse) from malware on purpose, while Malpedia lists every
    family as malware.
    """
    kinds: dict[str, str] = {}
    for record in sorted(software, key=lambda s: (s.source != "attack", s.source, s.source_id, s.kind)):
        for value in (record.name, *record.aliases):
            key = norm(value)
            if key and key not in actor_keys:
                kinds.setdefault(key, record.kind)
    return kinds
