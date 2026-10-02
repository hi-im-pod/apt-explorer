"""Name pairs that a vendor post states outright, such as "JADEPUFFER, tracked by Microsoft as Storm-3168".

A vendor names the same actor differently from everyone else, so a post titled with the vendor's ID
(Storm-3168) never meets the report that uses the actor's own name (JadePuffer). The post itself often
says they are one: "X, tracked by Microsoft as Y", "X, also known as Y". Those two names are the only
thing kept from the post. The sentence is read in memory and dropped, and the names are facts, not text.

What counts as a pair is deliberately narrow. Only phrases that equate two names are read. "Overlaps with",
"similar to" and "linked to" are not, because each says the two are different. Each side must be a name:
one to four capitalised words or a cluster ID, not a vendor, a place or a common word.

select() then decides which pairs may be published, against the registry built from every other source.
"""
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from aptx.resolve.names import norm
from aptx.resolve.title_terms import NOT_NAMES

# A name word: a capitalised word, a CamelCase or ALLCAPS word, or a cluster ID with a hyphen or digits.
_WORD = r"[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*"
_NAME = rf"{_WORD}(?:\s{_WORD}){{0,3}}"
_QUOTE = r"[\"“”'‘’]?"

# The words that equate two names. Longer phrases come first so the shorter ones do not cut them off.
_EQUATES = (
    r"(?:also\s+|previously\s+|formerly\s+)?(?:known|tracked|referred\s+to|called|reported|designated)\s+"
    r"(?:(?:by|as)\s+)?(?:[A-Z][A-Za-z]+\s+)?as"
    r"|(?:which\s+)?(?:[A-Z][A-Za-z]+\s+){0,2}tracks?\s+as"
    r"|a\.k\.a\.?|aka|also\s+dubbed|dubbed|formerly|previously"
)
_PAIR = re.compile(rf"(?P<left>{_NAME})\s*[,(;]\s*(?:{_EQUATES})\s+{_QUOTE}(?P<right>{_NAME}){_QUOTE}")

# Words that begin a sentence or a clause and are capitalised for that reason only.
_LEAD = frozenset({"the", "this", "that", "these", "those", "a", "an", "it", "its", "we", "our", "they", "their",
                   "he", "she", "in", "on", "at", "as", "by", "for", "from", "with", "and", "or", "but", "while",
                   "when", "after", "before", "during", "since", "once", "if", "also", "both", "each", "all"})
_MAX_LETTERS = 40
_MIN_LETTERS = 3
_ID_ONLY = re.compile(r"(?:CVE|CWE|MS|KB)[-\d]+|[\d.]+|[0-9a-f]{16,}", re.IGNORECASE)
# A vendor's own cluster label: Storm-3168, UNC2452, UAT-11587, DEV-0537, CL-STA-0048, GTG-20006.
_CLUSTER_ID = re.compile(r"(?:storm|unc|uat|uta|unk|uac|dev|tag|ta|fin|temp|ref|gtg|cl-[a-z]{3})[-\s]?\d{1,5}", re.IGNORECASE)


def is_cluster_id(name: str) -> bool:
    return _CLUSTER_ID.fullmatch(name.strip()) is not None


# A vendor numbers the clusters it has not yet tied to a known actor, and its own post titles are
# the one place that proves the number is the vendor's. Each format maps to the one source whose
# titles may name it. Other formats are left out on purpose: TA02, TA03 and TA16 are Proofpoint
# campaign numbers or product names that look the same, and a number without a vendor behind it
# says nothing. A hyphen is required, so "Dev 2024" in a headline is not a cluster.
CLUSTER_ISSUERS = {"UAT": "talos", "Storm": "microsoftblog", "DEV": "microsoftblog"}
_TITLE_CLUSTER = re.compile(r"(?<![A-Za-z0-9])(UAT|Storm|STORM|DEV)-(\d{4,5})(?![A-Za-z0-9])")


def title_clusters(title: str, source: str) -> list[str]:
    """The vendor cluster IDs `source` issues that `title` names, in the order written, each once."""
    out: list[str] = []
    for m in _TITLE_CLUSTER.finditer(title):
        prefix = "Storm" if m.group(1).casefold() == "storm" else m.group(1)
        name = f"{prefix}-{m.group(2)}"
        if CLUSTER_ISSUERS[prefix] == source and name not in out:
            out.append(name)
    return out


def _clean(side: str) -> str | None:
    """The side as a name, with a leading sentence word removed, or None when it is not one."""
    words = side.split()
    while words and words[0].casefold() in _LEAD:
        words.pop(0)
    if not words or len(words) > 4:
        return None
    name = " ".join(words)
    letters = sum(c.isalpha() for c in name)
    if not _MIN_LETTERS <= letters <= _MAX_LETTERS or _ID_ONLY.fullmatch(name):
        return None
    if any(w.casefold() in NOT_NAMES or w.casefold() in _LEAD for w in words):
        return None
    return name


def extract(text: str) -> list[tuple[str, str]]:
    """Every pair of names `text` says are one, in the order written, each pair once.

    The names are returned as written. Nothing else from the text is kept.
    """
    found: dict[tuple[str, str], tuple[str, str]] = {}
    for m in _PAIR.finditer(text):
        left, right = _clean(m.group("left")), _clean(m.group("right"))
        if left and right and norm(left) != norm(right):
            found.setdefault(tuple(sorted((norm(left), norm(right)))), (left, right))
    return list(found.values())


@dataclass(frozen=True)
class Decision:
    names: tuple[str, str]
    accepted: bool
    # "bridge" when one name is a published actor and the other is new to the registry, "new" when neither is known.
    kind: str
    reason: str

    @property
    def primary(self) -> str:
        """The name an actor is shown under: a vendor's cluster label is the alias, never the name."""
        a, b = self.names
        return b if is_cluster_id(a) and not is_cluster_id(b) else a

    @property
    def alias(self) -> str:
        return self.names[1] if self.primary == self.names[0] else self.names[0]


def select(pairs: Iterable[tuple[str, str]], lookup: Callable[[str], str | None],
           non_actor: Callable[[str], str | None], published: Mapping[str, object] | set[str],
           guess: Callable[[str], dict | None] | None = None) -> list[Decision]:
    """Which pairs may add an actor or an alias, judged against the registry of the other sources.

    `lookup` and `non_actor` are the registry's. `published` is the IDs of actors the site shows.
    `guess` scores a name nobody else lists, returning the guess row or None when there is no model.

    A pair is refused when:
      - either name belongs to software, because a malware family has no actor page;
      - the two names already belong to two different actors, because the post cannot make two
        groups one when the registry has them apart;
      - both names are unknown and either the pair has no vendor cluster ID (Storm-3168, UNC2452) or the
        name guesser does not call both names an actor. The guesser alone is not enough: measured on
        the paper's labelled names it calls almost any capitalised name an actor, malware families included.
    A name that is only a spelling of an unpublished actor is treated as unknown, since nothing shows it.
    """
    out = []
    for a, b in pairs:
        names = (a, b)
        kinds = [non_actor(n) for n in names]
        if any(kinds):
            out.append(Decision(names, False, "software", f"{names[kinds.index(next(k for k in kinds if k))]} is {next(k for k in kinds if k)}"))
            continue
        ids = [lookup(n) for n in names]
        ids = [i if i in published else None for i in ids]
        if ids[0] and ids[1]:
            same = ids[0] == ids[1]
            out.append(Decision(names, False, "known", "both names already belong to the same actor" if same
                                else "the names belong to two different actors"))
        elif ids[0] or ids[1]:
            out.append(Decision(names, True, "bridge", "one name is a published actor"))
        elif not any(is_cluster_id(n) for n in names):
            out.append(Decision(names, False, "new", "neither name is a vendor cluster ID, so nothing marks this as an actor"))
        elif guess is None:
            out.append(Decision(names, False, "new", "no guess model to check a new name"))
        else:
            rows = [guess(n) for n in names]
            if all(r and r["label"] == "actor" for r in rows):
                out.append(Decision(names, True, "new", "the name guesser calls both an actor"))
            else:
                label = ", ".join(f"{n}: {(r or {}).get('label', 'no guess')}" for n, r in zip(names, rows))
                out.append(Decision(names, False, "new", f"the name guesser does not call both an actor ({label})"))
    return out
