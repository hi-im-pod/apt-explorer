"""Measure the published data against the data-audit findings, without fetching anything.

    python -m aptx.audit [--data ../data] [--testset FILE] [--out FILE]

It reads data/reports/*.json and data/actors/index.json, applies the current rules for dates,
titles and CVEs after the fact, and prints counts for what is still open: duplicates, roundup
reports, generic site titles and publisher spellings. The numbers size the remaining fixes; a
real rebuild is still the final check.
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import urlsplit

from aptx.build.trends import UNTRUSTED_DATE_BASES, window_start_for
from aptx.core.dates import url_date
from aptx.core.report_titles import clean_title, is_error_page

ROUNDUP_ACTORS = 15
GENERIC_PAGES_PER_HOST = 4
MERGE_MAX_DAYS = 14
MERGE_MIN_CHARS = 20


def load(data: Path) -> tuple[list[dict], list[dict], str]:
    rows = [r for f in sorted((data / "reports").glob("*.json")) if f.stem != "index"
            for r in json.loads(f.read_text(encoding="utf-8"))]
    actors = json.loads((data / "actors" / "index.json").read_text(encoding="utf-8"))
    built = json.loads((data / "build.json").read_text(encoding="utf-8"))["built_at"]
    return rows, actors, built


def norm_title(title: str | None) -> str:
    return " ".join(re.sub(r"[\W_]+", " ", (clean_title(title) or "").casefold()).split())


def host(url: str | None) -> str:
    return (urlsplit(url or "").hostname or "").removeprefix("www.")


def redate(r: dict) -> tuple[str | None, str]:
    """The date and basis the current rules would give a published row."""
    if r["date_basis"] == "orkl-ingest":
        day = url_date(r["url"])
        if day and day <= r["published"]:
            return day, "url-date"
    return r["published"], r["date_basis"]


def trusted(r: dict) -> str | None:
    day, basis = redate(r)
    return None if basis in UNTRUSTED_DATE_BASES else day


def quarter(day: str) -> str:
    return f"{day[:4]}-Q{(int(day[5:7]) - 1) // 3 + 1}"


def _days(a: str, b: str) -> int:
    from datetime import date
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def generic_titles(rows: list[dict]) -> dict[str, list[dict]]:
    """Titles that four or more pages on one host share: a site's name, not a report's."""
    by = defaultdict(list)
    for r in rows:
        if (t := norm_title(r["title"])) and host(r["url"]):
            by[(t, host(r["url"]))].append(r)
    return {f"{h} | {t}": g for (t, h), g in by.items() if len(g) >= GENERIC_PAGES_PER_HOST}


def merge_candidates(rows: list[dict], generic: set[str]) -> list[list[dict]]:
    """Groups the strict duplicate rule would merge: one normalized title, dates within MERGE_MAX_DAYS."""
    by = defaultdict(list)
    for r in rows:
        t = norm_title(r["title"])
        if len(t) >= MERGE_MIN_CHARS and t not in generic:
            by[t].append(r)
    out = []
    for g in by.values():
        if len(g) < 2:
            continue
        dated = sorted((r for r in g if r["published"]), key=lambda r: r["published"])
        # Chain copies whose dates sit within the window of the previous copy.
        cluster = [dated[0]] if dated else []
        for r in dated[1:]:
            if _days(r["published"], cluster[-1]["published"]) <= MERGE_MAX_DAYS:
                cluster.append(r)
            else:
                if len(cluster) > 1:
                    out.append(cluster)
                cluster = [r]
        if len(cluster) > 1:
            out.append(cluster)
    return out


def measure(rows: list[dict], actors: list[dict], built: str, testset: set[str]) -> dict:
    start = window_start_for(built)
    today = built[:10]
    live = [r for r in rows if r["sources"] != ["paper"]]
    live_ids = {r["id"] for r in live}
    out: dict = {"build": built, "window_start": start, "records": len(rows)}

    # Dates: quarter totals of actor-linked live reports before and after the date rules.
    before, after = Counter(), Counter()
    for r in live:
        if not r["actors"]:
            continue
        if r["published"] and start <= r["published"] <= today:
            before[quarter(r["published"])] += len(r["actors"])
        if (d := trusted(r)) and start <= d <= today:
            after[quarter(d)] += len(r["actors"])
    out["activity_by_quarter"] = {q: {"before": before[q], "after": after[q]} for q in sorted(before | after)}
    out["redated_from_url"] = sum(redate(r)[1] == "url-date" and r["date_basis"] == "orkl-ingest" for r in rows)

    # Titles.
    out["titles_changed"] = sum(clean_title(r["title"]) != " ".join(r["title"].split()) for r in rows)
    out["titles_dropped"] = sum(clean_title(r["title"]) is None for r in rows)
    names = sorted({n.casefold() for a in actors for n in [a["name"], *a["aliases"]] if len(n) >= 4}, key=len)
    gained = lost = 0
    for r in rows:
        old, new = " ".join(r["title"].split()).casefold(), (clean_title(r["title"]) or "").casefold()
        if old == new:
            continue
        o = {n for n in names if re.search(rf"\b{re.escape(n)}\b", old)}
        w = {n for n in names if re.search(rf"\b{re.escape(n)}\b", new)}
        gained, lost = gained + len(w - o), lost + len(o - w)
    out["title_actor_names_estimate"] = {"gained": gained, "lost": lost}

    # CVEs a report could not cite, as the published data still carries them.
    out["cves_after_report_year_plus_1"] = sum(
        any(int(c[4:8]) > int(r["published"][:4]) + 1 for c in r["cves"]) for r in rows if r["published"])
    out["error_page_titles"] = sum(is_error_page(r["title"]) for r in rows)

    # Generic site titles, and what links rest on them.
    generic = generic_titles(rows)
    alias_words = {a["id"]: [n.casefold() for n in [a["name"], *a["aliases"]] if len(n) >= 4] for a in actors}
    hosts = []
    for key, g in sorted(generic.items(), key=lambda kv: -len(kv[1])):
        linked = [r for r in g if r["actors"]]
        in_slug = sum(any(any(re.sub(r"\W+", "-", n) in (r["url"] or "").casefold() for n in alias_words.get(a, []))
                          for a in r["actors"]) for r in linked)
        hosts.append({"title": key, "reports": len(g), "dates": len({r["published"] for r in g}),
                      "with_actors": len(linked), "actor_links": sum(len(r["actors"]) for r in g),
                      "from_text": sum(len(r["actors_from_text"]) for r in g),
                      "actor_in_url_slug": in_slug, "cves": sum(len(r["cves"]) for r in g),
                      "techniques": sum(len(r["techniques"]) for r in g)})
    out["generic_titles"] = {"groups": len(hosts), "reports": sum(h["reports"] for h in hosts), "by_title": hosts}

    # Duplicates.
    titles = defaultdict(list)
    for r in rows:
        if t := norm_title(r["title"]):
            titles[t].append(r)
    dup = {t: g for t, g in titles.items() if len(g) > 1}
    in_window = [g for g in dup.values()
                 if sum(bool(r["actors"] and r["id"] in live_ids and (d := trusted(r)) and start <= d <= today)
                        for r in g) > 1]
    generic_norm = {k.split(" | ", 1)[1] for k in generic}
    merges = merge_candidates(rows, generic_norm)
    renamed = [r["id"] for g in merges for r in g
               if r["id"] in testset and r["id"] != min((x["id"] for x in g if re.fullmatch(r"[0-9a-f]{40}", x["id"])),
                                                         default=r["id"])]
    out["duplicates"] = {
        "title_groups": len(dup), "surplus": sum(len(g) - 1 for g in dup.values()),
        "groups_counted_twice_in_window": len(in_window),
        "strict_merge_groups": len(merges), "strict_merge_surplus": sum(len(g) - 1 for g in merges),
        "strict_merge_with_paper_row": sum(any("paper" in r["sources"] for r in g) for g in merges),
        "testset_ids_renamed": renamed,
        "examples": [[(r["id"][:12], r["published"], r["title"][:60]) for r in g] for g in merges[:8]],
    }

    # Roundups.
    window_rows = [r for r in live if (d := trusted(r)) and start <= d <= today and r["actors"]]
    big = [r for r in window_rows if len(r["actors"]) >= ROUNDUP_ACTORS]
    out["roundups"] = {
        "all": sum(len(r["actors"]) >= ROUNDUP_ACTORS for r in rows), "in_window": len(big),
        "in_window_actor_links": sum(len(r["actors"]) for r in big),
        "in_window_all_actor_links": sum(len(r["actors"]) for r in window_rows),
        "examples": [(r["id"][:12], trusted(r), len(r["actors"]), len(r["techniques"]), r["title"][:60])
                     for r in sorted(big, key=lambda r: -len(r["actors"]))[:10]],
    }

    # Publishers.
    spellings = defaultdict(Counter)
    for r in rows:
        if o := r["organisation"]:
            spellings[re.sub(r"[\W_]+", "", o.casefold())][o] += 1
    variants = {k: dict(v) for k, v in spellings.items() if len(v) > 1}
    out["publishers"] = {"with_publisher": sum(bool(r["organisation"]) for r in rows),
                         "spelling_groups": len(variants), "spelling_rows": sum(sum(v.values()) for v in variants.values()),
                         "spellings": variants}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=Path("../data"))
    ap.add_argument("--testset", type=Path, default=Path("../research/stage2-labels/data/testset.json"))
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    rows, actors, built = load(a.data)
    tests = {t["id"] for t in json.loads(a.testset.read_text(encoding="utf-8"))} if a.testset.exists() else set()
    result = measure(rows, actors, built, tests)
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
