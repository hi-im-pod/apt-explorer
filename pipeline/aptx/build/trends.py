"""data/trends.json: what changed lately, computed from the assembled records.

compute() takes plain dicts, not source bundles, so it counts exactly what the
site will show. Assembly hands it only reports that are published and only
actors that have a file, and the paper's historical rows never reach it: the
trends schema promises the paper is a labelled historical layer that does not
feed current trends.

Every number here is a count of published records. Nothing is estimated, and
a rule that needs a date skips a record that has none, because a guessed date
would put a report into the wrong quarter without anyone seeing it.
"""
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

# Recent means the trailing 24 months, widened to whole quarters so no chart starts mid-quarter.
# Earlier reports only supply prev_year_count.
WINDOW_MONTHS = 24

# "New" means first seen within this many days of the build.
NEW_ACTOR_DAYS = 365

# Date bases that say when a source saw a report, not when it appeared. ORKL's ingest date put 5,083
# reports on 2026-04-06, the day of one bulk import, so counting them made that quarter look like a surge.
# A Wayback capture is the same kind of evidence: a recent capture of an old page is not recent reporting.
UNTRUSTED_DATE_BASES = frozenset({"orkl-ingest", "wayback-capture"})

_GENERATED_AT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")


def window_start_for(generated_at: str) -> str:
    """The first day of the quarter that holds the day WINDOW_MONTHS before the build.

    It depends only on the build timestamp, so rebuilding one snapshot gives the same window.
    """
    if not _GENERATED_AT.fullmatch(generated_at):
        raise ValueError(f"generated_at must be a UTC timestamp like 2026-09-30T04:00:00Z, got {generated_at!r}")
    year, month = int(generated_at[:4]), int(generated_at[5:7])
    back = year * 12 + (month - 1) - WINDOW_MONTHS
    year, month = divmod(back, 12)
    return date(year, month // 3 * 3 + 1, 1).isoformat()


def notes(window_start: str) -> dict[str, str]:
    """The counting rule printed under each chart.

    These are public copy. Each says what is counted and what is left out, so a
    reader can tell a quiet quarter from a gap in the sources.
    """
    return {
        "reporting_activity": (
            "Reports per quarter that are linked to at least one resolved actor, from the report sources "
            "only. Dated reports only: a report dated only by when ORKL added it or when the Wayback Machine saved "
            "it is left out, because that is not when it was published. Each quarter is compared with the same quarter a year earlier."),
        "new_actors": (
            f"Actors whose earliest date in any published source falls within {NEW_ACTOR_DAYS} days of this "
            f"build. A source that gives only a year counts only when that whole year falls inside the period."),
        "kev_monthly": (
            "CVEs CISA added to the KEV catalog each month, and how many KEV marks as known ransomware use."),
        "kev_actor_links": (
            f"KEV CVEs named in reports from {window_start} on that are also linked to a resolved actor. "
            f"A shared report, not an attribution."),
        "reported_vs_documented": (
            f"Technique IDs found in an actor's reports from {window_start} on, compared with the techniques "
            f"ATT&CK documents for that actor."),
        "source_health": (
            "Each source's newest good snapshot and record count. Stale means this build's fetch failed and "
            "the previous snapshot was used."),
    }


def _day(value: str) -> date:
    return date.fromisoformat(value)


def _quarter(d: date) -> str:
    return f"{d.year}-Q{(d.month - 1) // 3 + 1}"


def _quarter_start(q: str) -> date:
    year, n = q.split("-Q")
    return date(int(year), 3 * (int(n) - 1) + 1, 1)


def _year_on(q: str, years: int) -> str:
    year, n = q.split("-Q")
    return f"{int(year) + years}-Q{n}"


def compute(reports: list[dict], *, documented: dict[str, list[str]], vulns: list[dict],
            first_seen_claims: dict[str, list[tuple[str, str]]], source_health: list[dict],
            generated_at: str | None = None, window_start: str | None = None) -> dict:
    """Build the trends.json document.

    reports: the published reports as {"id", "published" (YYYY-MM-DD or None),
        "date_basis", "actors" (actor ids), "techniques", "cves"}. A report whose basis is
        in UNTRUSTED_DATE_BASES counts as undated here.
    documented: every published actor id mapped to the techniques ATT&CK
        documents for it, [] for an actor ATT&CK does not track. Its keys are the
        actors that have a file, and rows for any other actor are dropped so the
        site never links to a page that is not there.
    vulns: the published vulns.json records. Only cve, kev_date_added and
        ransomware are read.
    first_seen_claims: actor id to (YYYY-MM-DD, basis) pairs from the sources.
        A source that gives only a year passes January 1 with basis "year".
    source_health: the sources.json health rows, copied through unchanged.
    generated_at: YYYY-MM-DDTHH:MM:SSZ, injectable so a test or a rebuild of
        the same snapshot is byte-identical. Defaults to now.
    window_start: YYYY-MM-DD. Defaults to window_start_for(generated_at).
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not _GENERATED_AT.fullmatch(generated_at):
        raise ValueError(f"generated_at must be a UTC timestamp like 2026-09-30T04:00:00Z, got {generated_at!r}")
    today = _day(generated_at[:10])
    if window_start is None:
        window_start = window_start_for(generated_at)
    start = _day(window_start)
    published = set(documented)

    # A report dated after the build is a bad date, not news, so it counts for
    # nothing. An undated report has no quarter to belong to.
    dated = [(r, _day(r["published"])) for r in reports
             if r.get("published") and r.get("date_basis") not in UNTRUSTED_DATE_BASES]
    dated = [(r, d) for r, d in dated if d <= today and r.get("actors")]
    recent = [(r, d) for r, d in dated if d >= start]

    return {
        "window_start": window_start,
        "generated_at": generated_at,
        "reporting_activity": _reporting_activity(dated, published, start, today),
        "new_actors": _new_actors(dated, published, first_seen_claims, today),
        "kev_monthly": _kev_monthly(vulns, start, today),
        "kev_actor_links": _kev_actor_links(recent, vulns),
        "reported_vs_documented": _reported_vs_documented(recent, documented),
        "source_health": [dict(row) for row in source_health],
        "notes": notes(window_start),
    }


def _reporting_activity(dated, published, start: date, today: date) -> list[dict]:
    everything: dict[tuple[str, str], int] = defaultdict(int)
    current: dict[tuple[str, str], int] = defaultdict(int)
    for r, d in dated:
        for actor in set(r["actors"]) & published:
            everything[(actor, _quarter(d))] += 1
            if d >= start:
                current[(actor, _quarter(d))] += 1

    # A quarter gets a row when it has reports, and also when the same quarter a
    # year earlier had some, so a drop to silence shows as a row of 0 instead of
    # vanishing from the chart. A quarter that has not begun yet gets none. The
    # first quarter counts from its own first day, so a window starting inside a
    # quarter shows that quarter's reports from the window start on.
    first_quarter = _quarter(start)
    keys = set(current)
    for actor, q in everything:
        later = _year_on(q, 1)
        if _quarter_start(later) <= today:
            keys.add((actor, later))
    return [{"actor": actor, "quarter": q, "count": current.get((actor, q), 0),
             "prev_year_count": everything.get((actor, _year_on(q, -1)), 0)}
            for actor, q in sorted(keys) if q >= first_quarter]


def _new_actors(dated, published, claims, today: date) -> list[dict]:
    cutoff = today - timedelta(days=NEW_ACTOR_DAYS)
    seen: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for actor, pairs in claims.items():
        if actor in published:
            seen[actor].extend((d, basis) for d, basis in pairs if d and _day(d) <= today)
    for r, d in dated:
        for actor in set(r["actors"]) & published:
            seen[actor].append((d.isoformat(), "report"))
    out = []
    for actor in sorted(seen):
        if not seen[actor]:
            # Every claim was in the future, or the actor has none. With no date there is no
            # first sighting to compare with the window.
            continue
        # The earliest date from any source decides. A recent report does not make an
        # actor new when a source has known of it for years. Ties keep the source
        # key that sorts first, so the basis is the same on every build.
        first, basis = min(seen[actor])
        if _day(first) >= cutoff:
            out.append({"actor": actor, "first_seen": first, "basis": basis})
    return out


def _kev_monthly(vulns, start: date, today: date) -> list[dict]:
    added: dict[str, int] = defaultdict(int)
    ransomware: dict[str, int] = defaultdict(int)
    any_kev = False
    for v in vulns:
        if not v.get("kev_date_added"):
            continue
        any_kev = True
        d = _day(v["kev_date_added"])
        if start <= d <= today:
            added[v["kev_date_added"][:7]] += 1
            ransomware[v["kev_date_added"][:7]] += 1 if v.get("ransomware") is True else 0
    if not any_kev:
        # With no KEV data at all, a run of zeros would read as "CISA added nothing".
        return []
    out = []
    year, month = start.year, start.month
    while (year, month) <= (today.year, today.month):
        key = f"{year}-{month:02d}"
        out.append({"month": key, "added": added.get(key, 0), "ransomware": ransomware.get(key, 0)})
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def _kev_actor_links(recent, vulns) -> list[dict]:
    in_kev = {v["cve"] for v in vulns if v.get("kev_date_added")}
    links: dict[str, set[str]] = defaultdict(set)
    for r, _ in recent:
        for cve in r.get("cves", ()):
            if cve in in_kev:
                links[cve].update(r["actors"])
    return [{"cve": cve, "actors": sorted(links[cve])} for cve in sorted(links)]


def _reported_vs_documented(recent, documented) -> list[dict]:
    reported: dict[str, set[str]] = defaultdict(set)
    for r, _ in recent:
        for actor in r["actors"]:
            if actor in documented:
                reported[actor].update(r.get("techniques", ()))
    out = []
    for actor in sorted(reported):
        # An actor whose recent reports name no technique has nothing to compare, and
        # showing "0 overlap" would read as a mismatch with ATT&CK.
        if not reported[actor]:
            continue
        docs = set(documented[actor])
        out.append({"actor": actor, "reported_only": sorted(reported[actor] - docs),
                    "documented_only_count": len(docs - reported[actor]),
                    "overlap": len(docs & reported[actor])})
    return out
