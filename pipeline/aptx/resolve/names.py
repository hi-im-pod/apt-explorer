"""Name keys for matching actors across sources, and slugs for actor IDs.

Sources spell the same actor in many ways: "Lazarus Group", "LAZARUS",
"Lazarus-Group", or full-width "Ｌａｚａｒｕｓ" copied from an East Asian report.
norm() maps all of those to one key so the registry can see that they agree.
It must never merge names that differ in a digit, because APT2 and APT28 are
different groups.
"""
import re
import unicodedata

# \w keeps letters and digits in every script, plus the underscore. Everything
# else (spaces, hyphens, dots, dashes, full-width punctuation after NFKC) only
# separates tokens.
_NON_WORD = re.compile(r"[^\w]+")

# Sources disagree on whether "Group" or "Team" is part of a name ("Lazarus"
# against "Lazarus Group"), so a trailing one is dropped when it is not the
# whole name. "Team" alone stays, or it would have no key at all.
_SUFFIXES = frozenset({"group", "team"})


def words(text: str) -> list[str]:
    """The case-folded word tokens of a name or a title, before any suffix is dropped."""
    return _NON_WORD.sub(" ", unicodedata.normalize("NFKC", text).casefold()).split()


def capitalised_words(text: str) -> list[tuple[str, bool]]:
    """words(text), each with whether the word was written with a capital letter or a digit first.

    Prose and names differ in case: "Sandworm" is a name and "machete" is a tool. The tokens are
    exactly those words() returns, so an index into one is an index into the other.
    """
    out: list[tuple[str, bool]] = []
    for raw in _NON_WORD.sub(" ", unicodedata.normalize("NFKC", text)).split():
        flag = raw[0].isupper() or raw[0].isdigit()
        out.extend((w, flag) for w in _NON_WORD.sub(" ", raw.casefold()).split())
    return out


def norm(name: str) -> str:
    """The matching key for an actor or software name.

    NFKC folds full-width and other compatibility forms into plain ones, and
    casefold() is used rather than lower() so that, for example, Greek final
    sigma matches. Punctuation and spacing are dropped, so "APT 28", "apt-28"
    and "APT28" all become "apt28", while "APT2" stays "apt2". Names in other
    scripts keep their letters; they are case-folded, not transliterated.

    A name with no letters or digits returns "". Callers must skip that key,
    because every junk alias would otherwise share it and merge unrelated
    actors.
    """
    tokens = words(name)
    if len(tokens) > 1 and tokens[-1] in _SUFFIXES:
        tokens.pop()
    return "".join(tokens)


# Latin letters that NFKD does not split into a base letter and an accent, so
# the ASCII fold below would otherwise drop them and turn "Łódź" into "odz".
_FOLD = str.maketrans({
    "ø": "o", "ł": "l", "đ": "d", "ð": "d", "þ": "th", "æ": "ae", "œ": "oe",
    "ı": "i", "ħ": "h", "ŧ": "t", "ŋ": "n", "ĸ": "k", "ſ": "s",
})
_ASCII_WORD = re.compile(r"[a-z0-9]+")


def slug(name: str) -> str:
    """A lower-case ASCII slug of a display name, words joined by hyphens.

    Actor IDs become file names and URL segments, and the contract allows only
    [a-z0-9] runs joined by single hyphens. norm() keys are not usable for
    that: they keep the underscore and letters from any script. Accents are
    removed ("Café" becomes "cafe"), and characters with no ASCII form, such as
    Chinese or Cyrillic letters, are dropped, so the result can be "". The
    registry then tries another name, and it also keeps a slug away from
    reserved values such as "index".
    """
    folded = unicodedata.normalize("NFKC", name).casefold().translate(_FOLD)
    ascii_only = unicodedata.normalize("NFKD", folded).encode("ascii", "ignore").decode("ascii")
    return "-".join(_ASCII_WORD.findall(ascii_only))
