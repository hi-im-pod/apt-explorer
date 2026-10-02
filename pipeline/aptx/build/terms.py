"""data/terms.json: names that report titles keep repeating and that no source lists.

A title says who or what a report is about, so a name that many titles repeat, from more than one
publisher, may be an actor or a malware family the sources have not caught up with. This module
counts those names and runs each through the same scorer as the unresolved names in guesses.json.

A term never changes anything else. It is shown with its counts, three example titles and the
scorer's guess, and at most as "possibly the same as X". It is never promoted to an actor here.
Only a vendor post's stated name pair can add one (resolve/pairs.py).

Only titles the site already publishes are read, from the sources a page may show. The titles'
own words are the only text used: no post text is read or copied.
"""
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from aptx.build import guesses
from aptx.resolve.title_terms import Candidate, Title, TitleIndex, TitleStat

# A term is published only when this many reports carry it, from this many publishers. A name one
# vendor repeats in its own series is that vendor's label, not a name the field has settled on.
MIN_REPORTS = 3
MIN_PUBLISHERS = 2
EXAMPLES = 3

_SECOND_LEVEL = frozenset({"co", "com", "org", "net", "gov", "edu", "ac"})
_YEAR = re.compile(r"\d{4}")


def publisher_key(title: Title) -> str | None:
    """Who published the report: the organisation when the site shows one, else the host of its link.

    ORKL titles carry no organisation, so the link's registrable domain stands in for it.
    """
    if title.organisation and title.organisation.strip():
        return "org:" + title.organisation.strip().casefold()
    host = urlsplit(title.url or "").hostname
    if not host:
        return None
    labels = host.lower().removeprefix("www.").split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL:
        labels = labels[-3:]
    else:
        labels = labels[-2:]
    return "host:" + ".".join(labels)


def _examples(titles: Sequence[Title], indices: Iterable[int]) -> list[dict]:
    """Three titles with links, from different publishers first, newest first."""
    pool = sorted((titles[i] for i in indices if titles[i].url), key=lambda t: t.id)
    pool.sort(key=lambda t: t.published or "", reverse=True)
    chosen: list[Title] = []
    seen: set[str | None] = set()
    for t in pool:
        key = publisher_key(t)
        if key not in seen:
            chosen.append(t)
            seen.add(key)
    for t in pool:
        if len(chosen) >= EXAMPLES:
            break
        if t not in chosen:
            chosen.append(t)
    return [{"id": t.id, "title": t.text, "published": t.published, "organisation": t.organisation, "url": t.url}
            for t in chosen[:EXAMPLES]]


def _term(candidate: Candidate, stat: TitleStat, index: TitleIndex, prepared: guesses.Prepared) -> dict | None:
    titles = index.titles
    publishers = {publisher_key(titles[i]) for i in stat.indices} - {None}
    if stat.titles < MIN_REPORTS or len(publishers) < MIN_PUBLISHERS:
        return None
    dates = sorted(t.published for t in (titles[i] for i in stat.indices) if t.published)
    years = Counter(d[:4] for d in dates if _YEAR.fullmatch(d[:4]))
    name = candidate.name
    return {
        "name": name, "reports": stat.titles, "publishers": len(publishers),
        "first_seen": dates[0] if dates else None, "last_seen": dates[-1] if dates else None,
        "by_year": [{"year": int(y), "count": n} for y, n in sorted(years.items())],
        "shapes": sorted(candidate.shapes),
        "examples": _examples(titles, stat.indices),
        "guess": guesses.guess_name(name, stat.titles, prepared),
    }


def find_candidates(index: TitleIndex, is_known: Callable[[str], bool]) -> dict[str, Candidate]:
    """Name-shaped phrases the sources do not list, at least as frequent as a term needs."""
    return index.candidates(is_known, minimum_titles=MIN_REPORTS)


def build_terms(index: TitleIndex, candidates: Mapping[str, Candidate], stats: Mapping[str, TitleStat],
                prepared: guesses.Prepared | None) -> dict:
    """The contents of terms.json. Empty when there is no fitted model, because a guess needs one."""
    base = {"min_reports": MIN_REPORTS, "min_publishers": MIN_PUBLISHERS, "titles_read": len(index.titles)}
    if prepared is None:
        return {**base, "terms": [], "hidden_as_not_names": 0}
    terms: list[dict] = []
    hidden = 0
    for key, candidate in candidates.items():
        stat = stats.get(key)
        if stat is None:
            continue
        term = _term(candidate, stat, index, prepared)
        if term is None:
            continue
        if term["guess"]["label"] == "not-an-entity":
            hidden += 1
            continue
        terms.append(term)
    terms.sort(key=lambda t: (-t["reports"], -t["publishers"], t["name"].casefold()))
    return {**base, "terms": terms, "hidden_as_not_names": hidden}


def titles_from_reports(reports: Iterable) -> list[Title]:
    """The published titles that a source whose titles may be read supplied. A title that is only the link is skipped."""
    out = []
    for r in reports:
        if r.title_readable and r.url != r.title:
            out.append(Title(r.id, r.title, r.published, r.organisation, r.url))
    return out

