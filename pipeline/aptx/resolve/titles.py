"""Find the actors a report title names.

A link-only source keeps a title, a link and a date, never the post. A title that says
"Star Blizzard" is still a statement by the publisher about who the report is about, so the
build can read it, as long as it reads only what the site already publishes: the aliases of
published actors, from sources a page may show.

The matcher is deliberately cautious. A wrong link on a report is worse than a missing one.
  - It matches whole words only, longest name first, so "Cobalt Strike" is software and
    does not name the Cobalt group.
  - A name must resolve to this actor and no other, so an ambiguous alias matches nothing.
  - A single ordinary word ("Panda", "Silence", "Equation") is not a name on its own, so
    GENERIC is checked against a lone word in a title. The same word inside a longer name
    ("Equation Group", "Hacking Team") is a name, because the registry drops the trailing
    "Group" or "Team" when it compares names.
  - The registry compares "Hacking Team" and "Hacking Group" as the same name. Where the name
    is one ordinary word plus "Group" or "Team", the title must use the alias's own words.
  - A name with a digit (APT28, TA505, UNC1151), a Microsoft weather name (Star Blizzard,
    Storm-0558) or more than one word is specific enough to trust.
  - Some aliases name a malware family or a criminal service, which a title can mention without
    the report being about the actor. TOOLS lists them, and they never match.

The denylists come from measuring the matcher over every ORKL title (see the offline evaluation in
the build notes): each word is there because it matched titles that mean something else.
"""
from bisect import bisect_left
from collections.abc import Callable, Iterable, Mapping

from aptx.resolve.names import capitalised_words, norm, words

# The longest alias, in words, that is looked for in a title.
_MAX_WORDS = 5

_MIN_SINGLE_WORD = 5

# A report's text is read this far. A PDF can run to hundreds of thousands of words, and a name used only
# after this point is not what the report is about.
_MAX_TEXT_WORDS = 200_000

# Ordinary words and software or place names that are also an actor's name. A title is matched
# on one of these only as part of a longer name.
GENERIC: frozenset[str] = frozenset({
    "alibaba", "armageddon", "beijing", "bitter", "bookworm", "calisto", "chameleon", "chimera",
    "circles", "cobalt", "desktop", "dragonfly", "elfin", "equation", "fallout", "gorgon",
    "hacking", "hades", "harvester", "inception", "karma", "leviathan", "lookback", "longhorn",
    "monsoon", "moonlight", "nitro", "panda", "patchwork", "phantom", "platinum", "poseidon",
    "reaper", "scarab", "siesta", "silence", "slingshot", "snake", "sphinx", "strider", "summit",
    "mantis", "underground", "venom", "vermin",
    # Measured over ORKL's report text, where each is a browser, a wallet, a city or an ordinary noun.
    "castle", "chromium", "combine", "comment", "covenant", "electrum", "foxmail", "heartbeat", "mercury",
    "mirage", "navigator", "oxygen", "polaris", "shanghai", "silicon", "superman", "trident", "watchdog",
})

# Names of malware families, loaders and criminal services that a registry lists as an actor's
# alias. A title that names one is not saying the report is about the actor.
TOOLS: frozenset[str] = frozenset({
    "applejeus", "avalanche", "bazacall", "bazarcall", "blackenergy", "dnspionage", "fastcash",
    "goznym", "group5", "havex", "kinsing", "konni", "lummastealer", "lurid", "matanbuchus",
    "retefe", "seaduke", "shamoon", "sykipot",
})

# Aliases that are an ordinary phrase, so a title using the phrase is not naming the actor.
PHRASES: frozenset[str] = frozenset({"copypaste", "group3", "group6", "socialnetwork", "atk7"})


def _written_as_name(marked: list[tuple[str, bool]]) -> bool:
    """Whether the words were written as a name: capitalised, or carrying a digit.

    A trailing "group" or "team" is the writer's own word, not part of the name, so it may be lower case.
    """
    words_ = [w for w, _ in marked]
    if any(c.isdigit() for w in words_ for c in w):
        return True
    body = marked[:-1] if len(marked) > 1 and marked[-1][0] in ("group", "team") else marked
    return all(flag for _, flag in body)


def _usable(alias: str) -> bool:
    """Whether an alias is specific enough to find in a title."""
    tokens = words(alias)
    if not tokens or all(t.isdigit() for t in tokens):
        return False
    key = norm(alias)
    if key in TOOLS or key in PHRASES:
        return False
    if len(tokens) > 1:
        return len(key) >= 6 or any(c.isdigit() for c in key)
    return _single_word_ok(tokens[0])


def _single_word_ok(word: str) -> bool:
    """Whether one word, standing alone, is specific enough to be a name."""
    if any(c.isdigit() for c in word):
        return len(word) >= 4 and any(c.isalpha() for c in word)
    return len(word) >= _MIN_SINGLE_WORD and word not in GENERIC


class TitleMatcher:
    """Finds actor IDs in a title. Build one with build()."""

    def __init__(self, keys: Mapping[str, str], is_software: Callable[[str], bool],
                 spellings: Mapping[str, Iterable[tuple[str, ...]]] | None = None):
        self._keys = dict(keys)
        self._is_software = is_software
        self._spellings = {k: set(v) for k, v in (spellings or {}).items()}
        self._sorted = sorted(self._keys)

    def __bool__(self) -> bool:
        return bool(self._keys)

    def _fits(self, key: str, phrase: list[str]) -> bool:
        if len(phrase) == 1:
            return _single_word_ok(phrase[0])
        if key in GENERIC:
            return tuple(phrase) in self._spellings.get(key, ())
        return True

    def _may_start(self, token: str) -> bool:
        """Whether some name key begins with `token`, so a scan can skip a word that starts none."""
        i = bisect_left(self._sorted, token)
        return i < len(self._sorted) and self._sorted[i].startswith(token)

    def mentions(self, text: str) -> dict[str, dict]:
        """The names `text` uses, as {name: {"actor", "n", "at"}}.

        The same rules as match(), for running text instead of a title, with one more: a name
        must be written as a name. Prose says "machete" and "silence", so a word with no digit
        counts only when it is capitalised ("Machete"). `n` is how many times the name occurs and
        `at` is the word position of the first one, so a reader can tell an opening line from a
        passing reference. The name is the words as the matcher saw them, lower-cased.
        """
        marked = capitalised_words(text)[:_MAX_TEXT_WORDS]
        tokens = [w for w, _ in marked]
        found: dict[str, dict] = {}
        i = 0
        while i < len(tokens):
            if not self._may_start(tokens[i]):
                i += 1
                continue
            step = 1
            for n in range(min(_MAX_WORDS, len(tokens) - i), 0, -1):
                phrase = " ".join(tokens[i:i + n])
                if self._is_software(phrase):
                    step = n
                    break
                actor = self._keys.get(norm(phrase))
                if actor is not None and self._fits(norm(phrase), tokens[i:i + n]):
                    step = n
                    if _written_as_name(marked[i:i + n]):
                        hit = found.setdefault(phrase, {"actor": actor, "n": 0, "at": i})
                        hit["n"] += 1
                    break
            i += step
        return found

    def match(self, title: str) -> set[str]:
        tokens = words(title)
        found: set[str] = set()
        i = 0
        while i < len(tokens):
            step = 1
            for n in range(min(_MAX_WORDS, len(tokens) - i), 0, -1):
                phrase = " ".join(tokens[i:i + n])
                if self._is_software(phrase):
                    step = n
                    break
                actor = self._keys.get(norm(phrase))
                if actor is not None and self._fits(norm(phrase), tokens[i:i + n]):
                    found.add(actor)
                    step = n
                    break
            i += step
        return found


def build(aliases: Mapping[str, Iterable[str]], lookup: Callable[[str], str | None],
          is_software: Callable[[str], bool]) -> TitleMatcher:
    """A matcher over `aliases`, a mapping of actor ID to the alias values the site publishes.

    `lookup` is the registry's name resolution. An alias is kept only when it resolves to the
    actor that lists it, which drops every alias two actors share.
    """
    keys: dict[str, str] = {}
    spellings: dict[str, set[tuple[str, ...]]] = {}
    for actor, values in aliases.items():
        for value in values:
            # A key of digits alone ("3 1 3" for the 313 Team) is a number wherever it is written.
            if _usable(value) and not norm(value).isdigit() and lookup(value) == actor:
                keys[norm(value)] = actor
                spellings.setdefault(norm(value), set()).add(tuple(words(value)))
    return TitleMatcher(keys, is_software, spellings)
