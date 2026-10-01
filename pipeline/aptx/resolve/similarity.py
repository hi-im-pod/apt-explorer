"""Signals that say what an unresolved paper name probably is, computed from name text and reference data.

The resolver decides only by exact name keys, so a name it cannot match stays
unresolved: "apt sidewinder" against SideWinder, "keyboys" against KEYBOY, a
cluster ID nobody tracks yet, or a malware name a source spells differently.
This module reads such a name against the same reference data and reports
what looks similar, one signal at a time. It decides nothing. guesses.py turns
the signals into a label and a confidence, and only after an evaluation has
measured what each signal is worth.

Two rules keep the evaluation honest.
- The reference can be asked to leave a name out (`exclude_key`). Every
  ground-truth name was labelled because some source lists it, so scoring it
  against the full reference would let it match itself. Leaving its own key
  out shows how the signals do on a name no source knows, which is the
  situation of a real unresolved name.
- Report co-occurrence uses the paper's own report rows only. ORKL's actor tags
  are matching evidence under the licence notes and are never a signal here.

Every signal returns a plain sentence written by this code from its own
computed values. No source text is copied into it.
"""
import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from aptx.core.models import ReportRecord, SoftwareRecord
from aptx.resolve.names import norm
from aptx.resolve.registry import Registry

LABELS = ("actor", "malware", "tool", "not-an-entity")

# Cluster-naming conventions of the vendors that track groups by number before
# they have a name. The list follows the task brief plus the two numbered
# families every analyst knows, APT<number> and FIN<number>. It was fixed
# before any score was computed and was not extended afterwards to fit a miss.
_CLUSTER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("APT-C-NN", re.compile(r"apt[ -]?c[ -]?\d{2,3}")),
    ("APT<number>", re.compile(r"apt[ -]?\d{1,3}")),
    ("UNC<number>", re.compile(r"unc[ -]?\d{3,4}")),
    ("UAC-<number>", re.compile(r"uac[ -]?\d{3,4}")),
    ("TAG-<number>", re.compile(r"tag[ -]?\d{2,3}")),
    ("TA<number>", re.compile(r"ta[ -]?\d{3}")),
    ("DEV-<number>", re.compile(r"dev[ -]?\d{4}")),
    ("Storm-<number>", re.compile(r"storm[ -]?\d{3,4}")),
    ("FIN<number>", re.compile(r"fin[ -]?\d{1,2}")),
)

# Vendor naming conventions in which the last word says where a group is
# thought to operate from, or that it is a group at all.
_SUFFIX_WORDS = ("panda", "bear", "kitten", "chollima", "spider", "elephant", "typhoon", "blizzard",
                 "sandstorm", "group", "team")
_PREFIX_WORDS = ("water",)

# Words that name kinds of malware. A name ending in one of these is more often
# software than a group.
_MALWARE_WORDS = ("rat", "spy", "stealer", "loader", "banker", "ransomware", "botnet", "trojan", "backdoor",
                  "miner", "worm", "dropper", "implant", "rootkit", "keylogger", "malware")

# Words that describe a name without being part of it. Sources write "Emotet"
# and "Emotet gang" for one thing, so these are dropped to find the shared core.
_GENERIC = frozenset({"group", "team", "gang", "crew", "actor", "actors", "threat", "hackers", "hacker",
                      "attackers", "attacker", "apt", "campaign", "operation", "organization", "organisation"})

# Names that say nothing. Kept short and literal: it is a list of placeholder
# words, not a list of names anyone labelled.
_PLACEHOLDERS = frozenset({"unclassified", "unknown", "unattributed", "various", "others", "undisclosed"})
_CAMPAIGN_WORDS = ("operation", "campaign")

# A near miss is a spelling variant only when it differs by one or two edits
# and the names are long enough for that to mean something.
MIN_FUZZY_LENGTH = 5
MIN_FUZZY_SIMILARITY = 0.8

# How a source is named in a sentence a reader sees. The order is the order of the list.
_SOURCE_NAMES = {"attack": "ATT&CK", "misp": "MISP", "etda": "ETDA", "malpedia": "Malpedia", "orkl": "ORKL",
                 "kev": "CISA KEV", "dfir": "The DFIR Report", "paper": "the paper", "microsoft": "Microsoft", "epss": "EPSS"}

_NON_WORD = re.compile(r"[^\w]+")
_NUMBERS = re.compile(r"\d+")
_BRACKETS = re.compile(r"[(\[]([^)\]]+)[)\]]")
# A CVE that many groups use tells nothing about which one a report is about.
MAX_CVE_ACTORS = 3


def _tokens(text: str) -> list[str]:
    return _NON_WORD.sub(" ", unicodedata.normalize("NFKC", text).casefold()).split()


def _named(sources: Iterable[str]) -> str:
    """"ATT&CK, ETDA and Malpedia": source keys as a reader would write them, in a fixed order."""
    keys = set(sources)
    names = [n for k, n in _SOURCE_NAMES.items() if k in keys] + sorted(k for k in keys if k not in _SOURCE_NAMES)
    if not names:
        return "a source"
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def edit_distance(a: str, b: str, cap: int = 3) -> int:
    """Optimal string alignment distance, counting a swap of two neighbours as one edit.

    "hafnuim" against "hafnium" is one edit, which is what a typing slip looks
    like. Returns cap + 1 as soon as the distance must exceed cap, so scanning
    thousands of names stays fast.
    """
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev2: list[int] | None = None
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        best = cur[0]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            value = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                value = min(value, prev2[j - 2] + 1)
            cur[j] = value
            best = min(best, value)
        if best > cap:
            return cap + 1
        prev2, prev = prev, cur
    return min(prev[-1], cap + 1)


# The reference

@dataclass(frozen=True)
class ActorName:
    key: str
    actor_id: str
    actor_name: str
    spelling: str
    sources: frozenset[str]


@dataclass(frozen=True)
class SoftwareName:
    key: str
    kind: str
    spelling: str
    sources: frozenset[str]


@dataclass(frozen=True)
class Row:
    """One paper report row that names actors: the names as written, the actors they resolve to, its CVEs."""
    keys: tuple[str, ...]
    names: tuple[str, ...]
    actors: tuple[str | None, ...]
    cves: frozenset[str]


@dataclass
class Reference:
    actor_names: list[ActorName]
    software_names: list[SoftwareName]
    rows: list[Row]
    actor_display: dict[str, str]
    ambiguous: dict[str, list[str]]
    _actor_by_key: dict[str, list[ActorName]] = field(default_factory=dict, repr=False)
    _software_by_key: dict[str, list[SoftwareName]] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self._actor_by_key = defaultdict(list)
        for entry in self.actor_names:
            self._actor_by_key[entry.key].append(entry)
        self._software_by_key = defaultdict(list)
        for entry in self.software_names:
            self._software_by_key[entry.key].append(entry)

    def actors_with_key(self, key: str) -> list[ActorName]:
        return self._actor_by_key.get(key, [])

    def software_with_key(self, key: str) -> list[SoftwareName]:
        return self._software_by_key.get(key, [])

    def known_actor_ids(self, exclude_key: str | None = None) -> set[str]:
        """The actors that still have a name once `exclude_key` is left out."""
        return {e.actor_id for e in self.actor_names if e.key != exclude_key}


def build_reference(registry: Registry, software: Iterable[SoftwareRecord], paper_reports: Iterable[ReportRecord],
                    shown_sources: Iterable[str] | None = None) -> Reference:
    """The reference data as the signals read it.

    `shown_sources` limits the names to those from sources the site may
    publish from. A guess quotes the names it resembles, so a name that only an
    evidence-only source lists must not reach it. None means every source.

    Actor names come from the resolved registry, so an alias that any source
    lists under an actor counts. Software comes from the raw records because
    the registry keeps only a name-to-kind map. Only paper reports are used as
    rows: their actor names are the paper's own, where ORKL's are tags.
    """
    allowed = None if shown_sources is None else frozenset(shown_sources)
    actor_names: list[ActorName] = []
    display: dict[str, str] = {}
    for actor in registry.actors:
        display[actor.id] = actor.name
        by_key: dict[str, tuple[str, set[str]]] = {}
        for claim in actor.aliases:
            key = norm(claim.value)
            if not key or (allowed is not None and claim.prov.source not in allowed):
                continue
            spelling, sources = by_key.setdefault(key, (claim.value, set()))
            sources.add(claim.prov.source)
        for key, (spelling, sources) in by_key.items():
            actor_names.append(ActorName(key, actor.id, actor.name, spelling, frozenset(sources)))

    soft: dict[tuple[str, str], tuple[str, set[str]]] = {}
    for record in software:
        if allowed is not None and record.source not in allowed:
            continue
        for value in (record.name, *record.aliases):
            key = norm(value)
            if key:
                soft.setdefault((key, record.kind), (value, set()))[1].add(record.source)
    software_names = [SoftwareName(key, kind, spelling, frozenset(sources))
                      for (key, kind), (spelling, sources) in sorted(soft.items())]

    rows: list[Row] = []
    for report in paper_reports:
        if report.source != "paper" or not report.actor_names:
            continue
        rows.append(Row(
            keys=tuple(norm(n) for n in report.actor_names),
            names=tuple(report.actor_names),
            actors=tuple(registry.lookup(n) for n in report.actor_names),
            cves=frozenset(report.cves)))
    ambiguous = {a["alias"]: list(a["candidates"]) for a in registry.ambiguities}
    return Reference(actor_names, software_names, rows, display, ambiguous)


def only_actors(ref: Reference, names: Mapping[str, str]) -> Reference:
    """The reference with every actor outside `names` removed, and the given display names used.

    `names` maps an actor ID to the name the site shows for it. An actor the
    site does not publish has no page to link to, and a guess must not name one,
    so guesses are scored against the published actors only. The registry's own
    name for an actor can come from a source that may not be shown, so the
    published name is the one a guess quotes.
    """
    rows = [Row(r.keys, r.names, tuple(a if a in names else None for a in r.actors), r.cves) for r in ref.rows]
    return Reference([e for e in ref.actor_names if e.actor_id in names], ref.software_names, rows,
                     dict(names), ref.ambiguous)


# Name variants

@dataclass(frozen=True)
class Variant:
    key: str
    how: str  # a phrase that finishes "after ..."; empty for the name as written


def variants(name: str) -> list[Variant]:
    """The keys a name could be spelled as by another source, each with the reason.

    names.norm keeps a leading "apt " and a plural "s" on purpose, because
    dropping them everywhere would merge distinct groups. Here they are only a
    way to propose a match, which a reader can see and reject.
    """
    found: dict[str, str] = {}

    def add(key: str, how: str) -> None:
        # The resolver drops a trailing "group" or "team" from a key, so a
        # variant that keeps it differs from the key with no other change.
        if key and key not in found:
            found[key] = how or "keeping a trailing 'group' or 'team'"

    texts: list[tuple[str, str]] = [(name, "")]
    inner = _BRACKETS.findall(name)
    if inner:
        outer = _BRACKETS.sub(" ", name)
        texts = [(outer, "taking the part outside the brackets"), *[(i, "taking the part inside the brackets") for i in inner]]
    for text, how0 in texts:
        tokens = _tokens(text)
        if not tokens:
            continue
        stages: list[tuple[list[str], str]] = [(tokens, how0)]
        if len(tokens) > 1 and tokens[0] == "apt" and tokens[1].isalpha() and len(tokens[1]) >= 4:
            stages.append((tokens[1:], "removing the leading 'apt'"))
        core = [t for t in tokens if t not in _GENERIC]
        if core and len(core) < len(tokens):
            removed = sorted({t for t in tokens if t in _GENERIC})
            stages.append((core, "removing the word" + ("s " if len(removed) > 1 else " ") + " and ".join(f"'{t}'" for t in removed)))
        for stage_tokens, stage_how in stages:
            key = "".join(stage_tokens)
            add(key, stage_how)
            if len(key) >= 6 and key.endswith("s") and not key.endswith("ss"):
                add(key[:-1], (stage_how + " and " if stage_how else "") + "removing a plural 's'")
    base = norm(name)
    found.pop(base, None)
    return [Variant(k, h) for k, h in found.items()]


# Signals

# One plain sentence for each signal, for the evaluation table on the site.
SIGNALS: dict[str, str] = {
    "cluster_id": "The name follows a numbered cluster pattern such as UNC1234 or APT-C-15.",
    "vendor_suffix": "The name ends in a vendor naming word such as Panda, Bear or Team, or starts with Water.",
    "malware_word": "The name ends in a word that usually names malware, such as RAT, Spy or Loader.",
    "actor_resemblance": "The name is a close spelling of, or contains, the name of a known actor.",
    "software_resemblance": "The name is a close spelling of the name of known malware or a known tool.",
    "cooc_actor": "The paper lists the name in the same report row as an actor the resolver knows.",
    "cve_actor": "A report that uses the name cites a rare CVE that other reports tie to a known actor.",
    "non_latin": "The name is written in a script other than Latin.",
}

# Rules that pick a label outright. The ground truth has no example of either
# label, so the evaluation cannot say how often they are right.
RULES: dict[str, str] = {
    "placeholder_word": "The name is a placeholder word such as 'unclassified', not a name.",
    "campaign_word": "The name begins or ends with 'operation' or 'campaign', which names an operation, not an actor.",
    "exact_actor_name": "A source lists this exact name as an actor alias, and no source lists it as software.",
}


@dataclass(frozen=True)
class Hit:
    """The closest reference entry a name resembles, and how."""
    kind: str  # "variant", "contains" or "fuzzy"
    similarity: float
    spelling: str
    target: str  # an actor ID, or a software kind
    target_name: str  # the actor's display name, or the software spelling
    sources: frozenset[str]
    how: str


@dataclass(frozen=True)
class Evidence:
    signal: str
    detail: str


@dataclass
class Analysis:
    name: str
    key: str
    # Numeric signal values. 0.0 means the signal did not fire.
    features: dict[str, float]
    evidence: dict[str, Evidence]
    actor_hit: Hit | None
    software_hit: Hit | None
    related_actor: str | None
    hints: dict[str, str]
    # Whether a source lists the exact name as an actor alias, and the kinds of software it is listed as.
    exact_actor: bool = False
    exact_software: tuple[str, ...] = ()


def _rank(hit: Hit) -> tuple:
    return ({"variant": 2, "contains": 1, "fuzzy": 0}[hit.kind], hit.similarity)


def _core_text(spelling: str) -> str:
    """A name without its generic words, as written: "Winnti Group" gives "Winnti"."""
    words = [w for w in spelling.split() if w.casefold().strip("()[]") not in _GENERIC]
    return " ".join(words) or spelling


def _best_actor_hit(ref: Reference, name: str, key: str, exclude_key: str | None) -> Hit | None:
    hits: list[Hit] = []
    tokens = _tokens(name)
    for v in variants(name):
        for e in ref.actors_with_key(v.key):
            if e.key != exclude_key:
                hits.append(Hit("variant", 1.0, e.spelling, e.actor_id, e.actor_name, e.sources, v.how))
    for e in ref.actor_names:
        if e.key == exclude_key or e.key == key:
            continue
        ref_tokens = _tokens(e.spelling)
        ref_core = [t for t in ref_tokens if t not in _GENERIC] or ref_tokens
        length_ok = len(ref_core) >= 2 or (ref_core and len(ref_core[0]) >= 6)
        if length_ok and len(tokens) > len(ref_core) and _contiguous(ref_core, tokens):
            hits.append(Hit("contains", 0.9, e.spelling, e.actor_id, e.actor_name, e.sources, _core_text(e.spelling)))
            continue
        if _near_spelling(key, e.key):
            d = edit_distance(key, e.key, cap=2)
            sim = 1 - d / max(len(key), len(e.key))
            if d <= 2 and sim >= MIN_FUZZY_SIMILARITY:
                hits.append(Hit("fuzzy", round(sim, 3), e.spelling, e.actor_id, e.actor_name, e.sources, f"{d} edit" + ("s" if d > 1 else "")))
    return max(hits, key=lambda h: (_rank(h), h.target_name.casefold()), default=None)


def _best_software_hit(ref: Reference, name: str, key: str, exclude_key: str | None) -> Hit | None:
    hits: list[Hit] = []
    for v in variants(name):
        for e in ref.software_with_key(v.key):
            if e.key != exclude_key:
                hits.append(Hit("variant", 1.0, e.spelling, e.kind, e.spelling, e.sources, v.how))
    for e in ref.software_names:
        if e.key == exclude_key or e.key == key:
            continue
        if _near_spelling(key, e.key):
            d = edit_distance(key, e.key, cap=2)
            sim = 1 - d / max(len(key), len(e.key))
            if d <= 2 and sim >= MIN_FUZZY_SIMILARITY:
                hits.append(Hit("fuzzy", round(sim, 3), e.spelling, e.kind, e.spelling, e.sources, f"{d} edit" + ("s" if d > 1 else "")))
    return max(hits, key=lambda h: (_rank(h), h.target_name.casefold()), default=None)


def _near_spelling(a: str, b: str) -> bool:
    """Whether two keys are long enough, and agree on their digits, for an edit distance to mean a typo.

    norm() never merges names that differ in a digit, and neither may this:
    APT-C-15 and APT-C-17 are one edit apart and are different groups.
    """
    return a != b and min(len(a), len(b)) >= MIN_FUZZY_LENGTH and _NUMBERS.findall(a) == _NUMBERS.findall(b)


def _contiguous(needle: list[str], haystack: list[str]) -> bool:
    n = len(needle)
    return n > 0 and any(haystack[i:i + n] == needle for i in range(len(haystack) - n + 1))


def _cluster_kind(name: str) -> str | None:
    text = " ".join(_tokens(name))
    for label, pattern in _CLUSTER_PATTERNS:
        if pattern.fullmatch(text) or pattern.fullmatch(text.replace(" ", "-")) or pattern.fullmatch(text.replace(" ", "")):
            return label
    return None


def _suffix_word(name: str) -> str | None:
    tokens = _tokens(name)
    if not tokens:
        return None
    if tokens[0] in _PREFIX_WORDS and len(tokens) > 1:
        return tokens[0]
    last = tokens[-1]
    for word in _SUFFIX_WORDS:
        if last == word or (last.endswith(word) and len(last) > len(word) + 2 and len(tokens) == 1) \
                or (last.endswith(word) and len(last) > len(word) + 2 and last.isascii()):
            return word
    return None


def _malware_word(name: str) -> str | None:
    tokens = _tokens(name)
    if not tokens:
        return None
    last = tokens[-1]
    for word in _MALWARE_WORDS:
        if last == word or (last.endswith(word) and len(last) >= len(word) + 3):
            return word
    return None


def is_campaign_name(name: str) -> bool:
    tokens = _tokens(name)
    return bool(tokens) and (tokens[0] in _CAMPAIGN_WORDS or tokens[-1] in _CAMPAIGN_WORDS)


def is_placeholder(name: str) -> bool:
    tokens = _tokens(name)
    return len(tokens) == 1 and tokens[0] in _PLACEHOLDERS


def _script(name: str) -> str:
    """"latin" when every letter is Latin, else the first other script's name."""
    for ch in name:
        if ch.isalpha():
            label = unicodedata.name(ch, "")
            if not label.startswith("LATIN"):
                return label.split(" ")[0].casefold() or "other"
    return "latin"


def analyse(name: str, ref: Reference, exclude_key: str | None = None) -> Analysis:
    """Every signal for one name.

    `exclude_key` leaves that name key out of the reference names, so that a
    name with a known answer can be scored as if unknown. Report rows need no
    such step: co-occurrence skips the analysed name itself.
    """
    key = norm(name)
    features: dict[str, float] = {}
    evidence: dict[str, Evidence] = {}
    hints: dict[str, str] = {}

    cluster = _cluster_kind(name)
    features["cluster_id"] = 1.0 if cluster else 0.0
    if cluster:
        evidence["cluster_id"] = Evidence("cluster_id", f"The name follows the cluster-ID pattern {cluster}, which vendors use for groups they track by number.")

    suffix = _suffix_word(name)
    features["vendor_suffix"] = 1.0 if suffix else 0.0
    if suffix:
        evidence["vendor_suffix"] = Evidence("vendor_suffix", f"The name uses the vendor naming word '{suffix}', which appears in names of tracked groups.")

    mword = _malware_word(name)
    features["malware_word"] = 1.0 if mword else 0.0
    if mword:
        evidence["malware_word"] = Evidence("malware_word", f"The name ends in '{mword}', a word that usually names malware.")

    actor_hit = _best_actor_hit(ref, name, key, exclude_key)
    features["actor_resemblance"] = actor_hit.similarity if actor_hit else 0.0
    if actor_hit:
        if actor_hit.kind == "variant":
            text = f"The name matches the actor {actor_hit.target_name} (as '{actor_hit.spelling}') after {actor_hit.how}."
        elif actor_hit.kind == "contains":
            if actor_hit.how == actor_hit.spelling:
                text = f"The name contains '{actor_hit.spelling}', a name of the actor {actor_hit.target_name}."
            else:
                text = (f"The name contains '{actor_hit.how}', the distinctive part of '{actor_hit.spelling}', "
                        f"a name of the actor {actor_hit.target_name}.")
        else:
            text = f"The name is {actor_hit.how} away from '{actor_hit.spelling}', a name of the actor {actor_hit.target_name}."
        evidence["actor_resemblance"] = Evidence("actor_resemblance", text)

    software_hit = _best_software_hit(ref, name, key, exclude_key)
    features["software_resemblance"] = software_hit.similarity if software_hit else 0.0
    if software_hit:
        where = _named(software_hit.sources)
        if software_hit.kind == "variant":
            text = f"The name matches the {software_hit.target} '{software_hit.spelling}' listed by {where} after {software_hit.how}."
        else:
            text = f"The name is {software_hit.how} away from '{software_hit.spelling}', a {software_hit.target} listed by {where}."
        evidence["software_resemblance"] = Evidence("software_resemblance", text)

    own = [r for r in ref.rows if key in r.keys]
    others = [r for r in ref.rows if key not in r.keys]
    related: dict[str, int] = defaultdict(int)
    for r in own:
        for k, actor_id in zip(r.keys, r.actors):
            if k != key and actor_id:
                related[actor_id] += 1
    features["cooc_actor"] = 1.0 if related else 0.0
    related_actor = None
    if related:
        related_actor = sorted(related, key=lambda a: (-related[a], a))[0]
        evidence["cooc_actor"] = Evidence(
            "cooc_actor",
            f"A report in the paper's dataset lists this name together with {ref.actor_display.get(related_actor, related_actor)}.")

    own_cves = set().union(*(r.cves for r in own)) if own else set()
    cve_actors: dict[str, set[str]] = defaultdict(set)
    for r in others:
        for actor_id in r.actors:
            if actor_id:
                for cve in r.cves:
                    cve_actors[cve].add(actor_id)
    shared: dict[str, set[str]] = defaultdict(set)
    for cve in own_cves:
        actors = cve_actors.get(cve, set())
        if 0 < len(actors) <= MAX_CVE_ACTORS:
            for actor_id in actors:
                shared[actor_id].add(cve)
    features["cve_actor"] = 1.0 if shared else 0.0
    if shared:
        top = sorted(shared, key=lambda a: (-len(shared[a]), a))[0]
        cve = sorted(shared[top])[0]
        evidence["cve_actor"] = Evidence(
            "cve_actor", f"A report that uses this name cites {cve}, which the dataset's other reports tie to {ref.actor_display.get(top, top)}.")
        related_actor = related_actor or top

    script = _script(name)
    features["non_latin"] = 0.0 if script == "latin" else 1.0
    if script != "latin":
        hints["script"] = script

    exact_actor = any(e.key != exclude_key for e in ref.actors_with_key(key))
    exact_software = tuple(sorted({e.kind for e in ref.software_with_key(key) if e.key != exclude_key}))
    return Analysis(name=name, key=key, features=features, evidence=evidence, actor_hit=actor_hit,
                    software_hit=software_hit, related_actor=related_actor, hints=hints,
                    exact_actor=exact_actor, exact_software=exact_software)


def exact_presence(name: str, ref: Reference) -> list[Evidence]:
    """Where a source already lists this exact name.

    A name the resolver left unresolved can still be listed: as a name shared by
    two ATT&CK groups, for instance. The evaluation cannot measure this signal,
    since every ground-truth name is labelled because a source lists it, so
    leaving that source out removes the signal entirely.
    """
    key = norm(name)
    out: list[Evidence] = []
    actors = ref.actors_with_key(key)
    if actors:
        where = _named({s for e in actors for s in e.sources})
        out.append(Evidence("exact_actor_name", f"{where} list this exact name as an actor alias."))
    kinds = sorted({e.kind for e in ref.software_with_key(key)})
    if kinds:
        out.append(Evidence("exact_software_name", f"A source lists this exact name as {' and '.join(kinds)} software."))
    return out
