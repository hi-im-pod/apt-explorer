"""Frozen actor slugs, and the registry (data/slugs.json) that carries them from build to build.

An actor's slug is its ID and URL segment, so people bookmark it and link to it.
Two rules follow from that. It must come from the name the page displays and
from nothing else, because a slug built from a hidden alias would publish a name
the page is not allowed to show. And it must never change once published, even
when the display name changes or another source starts to know the actor.

Every build therefore reads the previous registry and recognises each actor by
its anchors: the identifiers of the source records the page is built from. An
anchor is "source:source_id", or the bare group ID for an ATT&CK group. It is a
record identifier, never an alias, so writing anchors to a public file does not
reveal a name either. An actor keeps the slug of the entry it shares anchors
with. If it shares anchors with several entries, the sources it was built from
were merged: it keeps the oldest slug, and the others are retired with a pointer
to the survivor, so their old addresses can say where the actor went.

A slug is never given out twice. Retired and vanished entries stay in the
registry, and a new actor whose natural slug is taken gets a numeric suffix,
which is recorded in the entry.

ATT&CK groups are the exception to "the slug comes from the name": their slug is
the group ID, which is already stable and public.
"""
import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from aptx.build.contract import load_schema
from aptx.resolve.names import slug as name_slug

REGISTRY_FILE = "slugs.json"

# The publish policies whose actor facts, and so whose names, a page may show.
# assemble() reads the same set, so the slug and the page cannot disagree on
# which members count.
SHOWS_FACTS = frozenset({"full", "derived-only"})

# Slugs that may never be used bare as actor IDs. "index" would overwrite
# actors/index.json. "g0007" would be the same file as G0007.json on the
# case-insensitive file systems of Windows and macOS.
RESERVED_SLUG = re.compile(r"index|g[0-9]{4}")

# Actor IDs become file names and URL segments, so very long names are cut to
# keep paths well inside Windows' limits.
MAX_ID_LENGTH = 64


@dataclass(frozen=True)
class Candidate:
    """A published actor of this build, as the slug assignment needs to see it."""
    # Any value that tells candidates apart; the registry uses the merge component's root.
    key: str
    # The name the page displays, from the published members only.
    name: str
    # Sorted identifiers of the published members. Never names.
    anchors: tuple[str, ...]
    # The ATT&CK group ID when ATT&CK tracks the actor. It is the slug.
    attack_id: str | None = None


def fit(base: str, suffix: str = "") -> str:
    """base with suffix, cut so the whole ID stays within MAX_ID_LENGTH.

    A cut can leave a trailing hyphen, which the ID pattern forbids, so it is
    removed.
    """
    return base[:MAX_ID_LENGTH - len(suffix)].rstrip("-") + suffix


def hidden_id(seed: str) -> str:
    """An ID for an actor that has nothing publishable.

    It never reaches data/, so it only has to be unique and stable within a
    build. It is a hash so that it cannot carry a name.
    """
    return "hidden-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]


def assign(candidates: Iterable[Candidate], previous: Iterable[Mapping], build_date: str) -> tuple[dict[str, str], list[dict]]:
    """The slug of every candidate, and the updated registry entries.

    `previous` is the entries of the registry the last build wrote. The result
    depends only on the set of candidates and on `previous`, so the order of
    the records cannot change a slug and a rebuild from the same sources gives
    the same registry.
    """
    prev: dict[str, dict] = {}
    for old in previous:
        if old["slug"] in prev:
            raise ValueError(f"{REGISTRY_FILE}: slug {old['slug']!r} appears twice")
        prev[old["slug"]] = dict(old)
    # An entry that was merged away stays a redirect for good. Giving its address to a
    # fragment of a later split would send visitors of the old link to a different actor.
    matchable = {s: e for s, e in prev.items() if e["merged_into"] is None}
    by_anchor: dict[str, set[str]] = defaultdict(set)
    for s, e in matchable.items():
        for anchor in e["anchors"]:
            by_anchor[anchor].add(s)

    ordered = sorted(candidates, key=lambda c: (c.anchors, c.key))
    if len({c.key for c in ordered}) != len(ordered):
        raise ValueError("two candidates share a key")

    # Each entry belongs to the one candidate that shares the most anchors with it, so a split
    # leaves the slug with the larger half. Ties go to the candidate with the smaller anchors,
    # which is fixed by the data and not by the order the records arrived in.
    claims: dict[str, list[tuple[int, int, str]]] = defaultdict(list)
    for rank, c in enumerate(ordered):
        for s, n in Counter(s for a in c.anchors for s in by_anchor.get(a, ())).items():
            claims[s].append((-n, rank, c.key))
    owner = {s: min(found)[2] for s, found in claims.items()}
    owned: dict[str, list[str]] = defaultdict(list)
    for s, key in owner.items():
        owned[key].append(s)

    result: dict[str, str] = {}
    retired_into: dict[str, str] = {}
    fresh: list[Candidate] = []
    for c in ordered:
        mine = sorted(owned.get(c.key, ()), key=lambda s: (prev[s]["first_published"], s))
        if c.attack_id:
            # An ATT&CK group keeps its group ID, which is what its file and links already use.
            # A slug the group swallowed becomes a redirect to it.
            slug = c.attack_id
        elif mine:
            slug = mine[0]
        else:
            fresh.append(c)
            continue
        result[c.key] = slug
        for s in mine:
            if s != slug:
                retired_into[s] = slug

    taken = set(prev) | set(result.values())
    suffixes: dict[str, int | None] = {}
    numbered: list[tuple[Candidate, str]] = []
    for c in fresh:
        # A name with no ASCII form gives no slug. A hash of the anchors stays the same from one
        # build to the next, where a running number would not, and it cannot carry a hidden name.
        base = fit(name_slug(c.name)) or "actor-" + hashlib.sha1("\n".join(c.anchors).encode("utf-8")).hexdigest()[:10]
        # Every natural slug is given out before any numbered one, so "Muller Cat 2" keeps
        # muller-cat-2 even when a second "Muller Cat" needs a number.
        if base in taken or RESERVED_SLUG.fullmatch(base):
            numbered.append((c, base))
        else:
            result[c.key] = base
            suffixes[c.key] = None
            taken.add(base)
    for c, base in numbered:
        n = 2
        while (candidate := fit(base, f"-{n}")) in taken:
            n += 1
        result[c.key] = candidate
        suffixes[c.key] = n
        taken.add(candidate)

    entries: dict[str, dict] = {}
    for c in ordered:
        slug = result[c.key]
        old = prev.get(slug)
        entries[slug] = {
            "slug": slug,
            "display_name": c.name,
            "anchors": list(c.anchors),
            "first_published": old["first_published"] if old else build_date,
            "suffix": old["suffix"] if old else suffixes.get(c.key),
            "retired": False,
            "merged_into": None,
        }
    for s, old in prev.items():
        if s not in entries:
            entries[s] = {**old, "retired": True, "merged_into": retired_into.get(s, old["merged_into"])}
    _resolve_chains(entries)
    return result, [entries[s] for s in sorted(entries)]


def _resolve_chains(entries: dict[str, dict]) -> None:
    """Point every merged entry at the end of its chain, so a retired page needs one hop.

    When the actor an entry was merged into is itself merged into an older one later, a
    visitor of the first old address should land on the actor that exists now.
    """
    for entry in entries.values():
        target, seen = entry["merged_into"], {entry["slug"]}
        while target in entries and entries[target]["merged_into"] is not None and target not in seen:
            seen.add(target)
            target = entries[target]["merged_into"]
        entry["merged_into"] = target


def document(entries: Iterable[Mapping]) -> dict:
    """The value of data/slugs.json for these entries."""
    return {"entries": [dict(e) for e in sorted(entries, key=lambda e: e["slug"])]}


def shown_sources(policies: Mapping[str, str]) -> frozenset[str]:
    """The sources whose members may name a page, from the publish policies."""
    return frozenset(source for source, policy in policies.items() if policy in SHOWS_FACTS)


def document_for_build(registry, policies: Mapping[str, str]) -> dict:
    """data/slugs.json for a build, refusing a registry that was told the wrong sources.

    The slugs and anchors were derived from the members the registry was allowed to see. When
    that is not the set the publish policies allow, a hidden source may have shaped a slug or an
    anchor, and the build must stop rather than publish it.
    """
    members = {m.source for actor in registry.actors for m in actor.members}
    allowed = {s for s in members if policies.get(s) in SHOWS_FACTS}
    used = members if registry.shown_sources is None else members & registry.shown_sources
    if used != allowed:
        raise ValueError(
            "the registry was resolved with different visible sources than the publish policies allow "
            f"({sorted(used - allowed)} used but not shown, {sorted(allowed - used)} shown but unused); "
            "pass shown_sources=slugs.shown_sources(policies) to resolve()")
    return document(registry.slug_entries)


def read_registry(path: Path | str) -> list[dict]:
    """The entries of the registry at `path`, or none when there is no file yet.

    A file that does not match the schema is an error, not an empty registry: starting again
    from nothing would hand every actor a fresh slug and break the published addresses.
    """
    path = Path(path)
    if not path.is_file():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ValueError(f"{path}: cannot be read as JSON ({e})") from e
    errors = sorted(Draft202012Validator(load_schema("slugs")).iter_errors(doc),
                    key=lambda e: [str(p) for p in e.absolute_path])
    problems = [f"{'/'.join(str(p) for p in e.absolute_path) or '(whole file)'}: {e.message[:200]}" for e in errors[:5]]
    if not problems:
        problems = structure_problems(doc)
    if problems:
        raise ValueError(f"{path}: not a valid slug registry:\n  " + "\n  ".join(problems))
    return doc["entries"]


def structure_problems(doc: Mapping) -> list[str]:
    """Problems inside the registry itself, whatever the actors are."""
    problems: list[str] = []
    entries = doc["entries"]
    by_slug: dict[str, Mapping] = {}
    for e in entries:
        slug = e["slug"]
        if slug in by_slug:
            problems.append(f"slugs.json: {slug} appears twice")
        by_slug[slug] = e
    for slug, e in sorted(by_slug.items()):
        if e["anchors"] != sorted(e["anchors"]):
            problems.append(f"slugs.json: {slug}: anchors are not sorted")
        if e["suffix"] is not None and not slug.endswith(f"-{e['suffix']}"):
            problems.append(f"slugs.json: {slug}: suffix {e['suffix']} is not the end of the slug")
        target = e["merged_into"]
        if target is None:
            continue
        if not e["retired"]:
            problems.append(f"slugs.json: {slug}: has merged_into but is not retired")
        elif target == slug or target not in by_slug:
            problems.append(f"slugs.json: {slug}: merged_into {target!r} is not another entry")
        elif by_slug[target]["merged_into"] is not None:
            problems.append(f"slugs.json: {slug}: merged_into {target} is itself merged away, "
                            "so the chain is not resolved")
    return problems


def cross_problems(actor_names: Mapping[str, str], doc: Mapping) -> list[str]:
    """Contradictions between the registry and the published actors.

    `actor_names` maps every published actor ID to the name its file shows. Every actor must
    have an active entry, and every active entry must be a published actor, so a page can never
    exist without a frozen slug and a slug can never claim a page that is not there.
    """
    problems = structure_problems(doc)
    by_slug = {e["slug"]: e for e in doc["entries"]}
    for actor_id in sorted(actor_names):
        e = by_slug.get(actor_id)
        if e is None:
            problems.append(f"actors/{actor_id}.json: slugs.json has no entry for {actor_id}")
        elif e["retired"]:
            problems.append(f"slugs.json: {actor_id} is retired but is a published actor")
        elif e["display_name"] != actor_names[actor_id]:
            problems.append(f"slugs.json: {actor_id} is named {e['display_name']!r} there but "
                            f"{actor_names[actor_id]!r} in its actor file")
    for slug, e in sorted(by_slug.items()):
        if not e["retired"] and slug not in actor_names:
            problems.append(f"slugs.json: {slug} is active but is not a published actor")
    return problems


def today() -> str:
    """The build date to record when the caller gives none."""
    return datetime.now(timezone.utc).date().isoformat()
