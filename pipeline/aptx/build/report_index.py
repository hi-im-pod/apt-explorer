"""The compact index of every report that the explore page loads first.

The full report shards hold about 21 MB of JSON, and the explore table needs
only a few fields of each report to list, filter and search it. This module
turns all reports into one columnar file: one array per field, the same
position in every array meaning the same report, with repeated strings
(publishers, actors, CVEs, techniques, source keys) stored once in tables and
referred to by position. The result is about a twentieth of the shards' size
compressed, and the page fetches the full record of one report from its year
shard only when a visitor opens it.

Everything here is deterministic for a given set of reports, and the write
step rebuilds the index from the shards and demands an exact match, so the
index cannot drift from the reports it summarises.
"""
import re
from collections import Counter
from collections.abc import Iterable, Mapping

# A report ID that is a SHA-1 digest. Any other ID looks like "<source>:<source_id>".
_SHA = re.compile(r"[0-9a-f]{40}")

# Ids are cut to the shortest prefix that is unique, but never below this.
# Eight hex characters is already 4 billion values, and a floor stops one
# unusually lucky build from publishing links that a later build would break.
MIN_ID_LEN = 8


def short_id(report_id: str, id_len: int) -> str:
    """The form of a report ID that the index stores.

    A digest is cut to `id_len` characters, which is what keeps the id column
    small. Any other ID is kept whole, because there are few of them and they
    carry no random part to cut down to.
    """
    return report_id[:id_len] if _SHA.fullmatch(report_id) else report_id


def _id_len(ids: Iterable[str]) -> int:
    digests = [i for i in ids if _SHA.fullmatch(i)]
    for length in range(MIN_ID_LEN, 41):
        if len({d[:length] for d in digests}) == len(digests):
            return length
    return 40  # Unreachable while ids are unique, because full digests are then distinct.


def _by_frequency(values: Iterable[str]) -> list[str]:
    """Distinct values, most common first, ties alphabetical.

    Common values get small numbers, and small numbers are short in the JSON,
    so the same count of references costs fewer bytes.
    """
    counts = Counter(values)
    return sorted(counts, key=lambda v: (-counts[v], v))


def build_reports_index(reports: Iterable[Mapping], *, kev_cves: Iterable[str], built_at: str) -> dict:
    """The index for `reports`, which are the rows of every report shard in any order.

    `kev_cves` are the CVEs in the KEV catalogue, so the page can mark a report
    without loading the whole vulnerability list. `built_at` is the time in
    build.json, which lets the page notice an index and a build.json that come
    from different builds.
    """
    # Newest first with undated reports last, then by title and id. The table
    # shows this order as it is, so the browser never sorts thirty thousand
    # rows, and reports of one day still read alphabetically.
    rows = sorted(reports, key=lambda r: (r["published"] is None, _negate(r["published"]), r["title"].casefold(),
                                          r["id"]))
    ids = [r["id"] for r in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("a report id appears more than once, so the index cannot address it")
    id_len = _id_len(ids)

    sources = _by_frequency(s for r in rows for s in r["sources"])
    organisations = _by_frequency(r["organisation"] for r in rows if r["organisation"] is not None)
    actors = _by_frequency(a for r in rows for a in r["actors"])
    cves = _by_frequency(c for r in rows for c in r["cves"])
    techniques = _by_frequency(t for r in rows for t in r["techniques"])
    at = {name: {v: i for i, v in enumerate(table)} for name, table in
          (("sources", sources), ("organisations", organisations), ("actors", actors), ("cves", cves),
           ("techniques", techniques))}

    kev = set(kev_cves)
    return {
        "built_at": built_at,
        "id_len": id_len,
        "total": len(rows),
        "tables": {"sources": sources, "organisations": organisations, "actors": actors, "cves": cves,
                   "techniques": techniques},
        "kev": sorted(at["cves"][c] for c in cves if c in kev),
        "columns": {
            "id": [short_id(r["id"], id_len) for r in rows],
            "title": [r["title"] for r in rows],
            "published": [r["published"] for r in rows],
            "organisation": [None if r["organisation"] is None else at["organisations"][r["organisation"]]
                             for r in rows],
            "sources": [sum(1 << at["sources"][s] for s in r["sources"]) for r in rows],
            "actors": [sorted(at["actors"][a] for a in r["actors"]) for r in rows],
            "actors_from_title": [sorted(at["actors"][a] for a in r["actors_from_title"]) for r in rows],
            "cves": [sorted(at["cves"][c] for c in r["cves"]) for r in rows],
            "techniques": [sorted(at["techniques"][t] for t in r["techniques"]) for r in rows],
        },
    }


def _negate(published: str | None) -> str:
    """A sort key that puts later dates first when compared as text.

    Dates are fixed-width YYYY-MM-DD, so mapping each digit d to 9-d reverses
    the order without needing a date parser. The dash stays as it is.
    """
    if published is None:
        return ""
    return "".join(str(9 - int(ch)) if ch.isdigit() else ch for ch in published)
