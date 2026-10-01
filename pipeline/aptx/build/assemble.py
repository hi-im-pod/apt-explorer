"""Assemble every file of data/ from the connectors' records, the registry and the publish policies.

This module is the one place that decides what the public data says. The
connectors normalize each source into records, the registry merges actor
records into actors, and assemble() turns both into the payload that
write.write_all() checks and writes. It does no I/O and no fetching, so a
test can run it on in-memory records and a rebuild of the same snapshot gives
the same payload.

Call it like this (Task 14's CLI does):

    payload = assemble(bundles, registry, policies, link_status=None, generated_at=None, *, facts=facts)
    write.write_all(out, payload)

bundles: one SourceBundle per source, as a dict from source key to bundle or as a
    list keyed by bundle.source. A source with no bundle counts as empty. A
    source key outside notice.SOURCE_ORDER, or two bundles for one source, is
    an error.
registry: resolve(all actor records, all software records). It must be given
    the records of every source, evidence-only ones included, because the
    merge uses them. assemble() decides what may be shown.
policies: source key to the publish policy string, one per key in
    notice.SOURCE_ORDER, from connector.policy(store) called once per source
    this build ("full", "derived-only", "link-only" or "evidence-only"). A
    missing key or an unknown value raises ValueError. The build fails
    closed, because a source with no policy could otherwise be published.
link_status: a URL, or a norm_url, mapped to True or False from the link
    check. Missing means "not checked", so url_ok is null.
generated_at: YYYY-MM-DDTHH:MM:SSZ. Defaults to now. Injecting it makes a
    rebuild byte-identical.
facts: a BuildFacts (below), the inputs that do not come from the records.

The return value is the flat payload write.write_all() takes: "actors/index.json",
"actors/<id>.json", "reports/<year>.json", "reports/undated.json" (always
present), "campaigns.json", "vulns.json", "sources.json", "resolution.json",
"trends.json", "build.json", each mapped to its JSON value, and "NOTICE.md"
mapped to its text.

What each policy lets through:

    full          actor facts, reports and everything else are published.
    derived-only  the same, since the connector has already reduced the record to
                  derived facts (ETDA and Malpedia).
    link-only     report metadata and links only. Nothing the source says about an
                  actor is published, and its tags attach no report to an actor. A
                  vendor's own title may still name one (see below).
    evidence-only merge evidence only. Nothing from the source is published, but
                  the edges it caused still count in evidence_count.

Report-to-actor links come from four places, so a source that may not be shown can
never decide an attribution: Malpedia's report_links (when Malpedia is publishable),
the group references in ATT&CK, the actor names the paper gives for its own reports,
and a title that names a published actor. The first three are tags. The fourth is
weaker and is kept apart as actors_from_title: a link-only source keeps no post, only
its title, so the title is all there is to read. Only the title the site shows is read,
and only when it comes from a source in TITLE_MATCH_SOURCES, and only for the aliases
the site already publishes (resolve/titles.py). ORKL's actor tags are matching evidence and are
ignored here even when its policy is widened, and its titles are not read.
"""
import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations

from aptx.build import guesses, slugs, trends
from aptx.build.countries import country_name, iso2
from aptx.build.notice import SOURCE_INFO, SOURCE_ORDER, render_notice, require_year, source_attribution
from aptx.build.report_index import build_reports_index
from aptx.core.dates import parse_date
from aptx.core.models import ActorRecord, CampaignRecord, ReportRecord, SourceBundle, VulnRecord
from aptx.core.urls import norm_url
from aptx.resolve import titles
# _display_name is private to the registry, but assembly must name an actor from the
# members it may show. The registry's own name can come from an evidence-only source.
from aptx.resolve.registry import Registry, ResolvedActor, _display_name

# Kept in step with pipeline/pyproject.toml. Task 14 may pass the installed version instead.
PIPELINE_VERSION = "0.1.0"

POLICY_VALUES = frozenset({"full", "derived-only", "link-only", "evidence-only"})
_SHOWS_FACTS = frozenset({"full", "derived-only"})
_SHOWS_REPORTS = frozenset({"full", "derived-only", "link-only"})
_ORD = {key: i for i, key in enumerate(SOURCE_ORDER)}

# Sources whose report titles may name an actor. ORKL is left out on purpose: its 29,000 titles
# are the bulk of the data, and its titles have not been judged for this yet.
TITLE_MATCH_SOURCES = frozenset({"microsoftblog", "talos", "eset", "dfir", "paper"})

_GENERATED_AT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_URL = re.compile(r"https?://\S+")
_CVE = re.compile(r"CVE-[0-9]{4}-[0-9]{4,7}")
_TECHNIQUE = re.compile(r"T[0-9]{4}(\.[0-9]{3})?")
_GROUP_ID = re.compile(r"G[0-9]{4}")
_SHA1 = re.compile(r"[0-9a-f]{40}")
_CAMPAIGN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")
_YEAR_ONLY = re.compile(r"(19|20)[0-9]{2}")
_WHITESPACE = re.compile(r"\s")

MAX_SECTOR_LENGTH = 80
MAX_UNRESOLVED_NAMES = 200

# Where a report's title, organisation and original URL come from when sources
# disagree: the publisher's own feed first, then ORKL, then the paper's dataset.
_REPORT_PRIORITY = {"dfir": 0, "talos": 0, "eset": 0, "microsoftblog": 0, "orkl": 1, "paper": 2}

# Which date wins when records of one report disagree, best evidence first.
_BASIS_RANK = {"publisher": 0, "malpedia-library": 1, "paper": 2, "title-date": 3, "file-metadata": 4, "orkl-ingest": 5}


@dataclass(frozen=True)
class BuildFacts:
    """The inputs to a build that do not come from the source records.

    copyright_year and valid_techniques are required, and Task 14 must supply them:
    the year is what attack.copyright_year(store) read from MITRE's licence file, and
    valid_techniques is the set of ATT&CK technique and sub-technique IDs the
    reports' technique lists are checked against. Everything else has a default that
    means "not available in this build".
    """
    copyright_year: str
    valid_techniques: frozenset[str]
    # Source key to the YYYY-MM-DD date of the newest good snapshot (store.latest_date).
    snapshot_dates: Mapping[str, str | None] = field(default_factory=dict)
    # etda.last_db_change(store). ETDA's snapshot is fetched fresh while its database has
    # been frozen for a long time, so its own change date is the honest "last success".
    etda_last_db_change: str | None = None
    # attack.group_reference_urls(store): group ID to the report URLs ATT&CK cites for it.
    group_reference_urls: Mapping[str, list[str]] = field(default_factory=dict)
    # Malpedia's report_links: a report URL to the actor names Malpedia files it under.
    malpedia_report_links: Mapping[str, list[str]] = field(default_factory=dict)
    # Every actor name in the paper's report data, for the match rate in resolution.json.
    paper_names: Iterable[str] = ()
    # Sources whose fetch failed this build, so the previous snapshot was used.
    fetch_failed: frozenset[str] = frozenset()
    version: str = PIPELINE_VERSION
    # The labelled set of paper names (guesses.read_labels). Its derived and confirmed rows are the
    # ground truth that guesses.json is measured on. Empty means "no ground truth", and then
    # guesses.json is written with no evaluation and no guesses.
    guess_labels: tuple = ()


def assemble(bundles, registry: Registry, policies: Mapping[str, str], link_status: Mapping[str, bool] | None = None,
             generated_at: str | None = None, *, facts: BuildFacts,
             title_sources: frozenset[str] = TITLE_MATCH_SOURCES) -> dict:
    """The payload for write.write_all(), or a ValueError when the inputs cannot make one safely."""
    generated_at = _timestamp(generated_at)
    year = require_year(facts.copyright_year)
    policies = _check_policies(policies)
    by_source = _bundles_by_source(bundles)
    today = generated_at[:10]
    window_start = trends.window_start_for(generated_at)
    valid_techniques = frozenset(facts.valid_techniques)

    shown = _published_actors(registry, policies)
    published_ids = {p.id for p in shown}

    # Only the aliases a page shows are read, so a title can never reveal a name that only an
    # evidence-only source holds.
    matcher = titles.build(
        {p.id: [a["value"] for a in _aliases(p, _display_name(p.members), {m.source for m in p.members}.__contains__)]
         for p in shown},
        registry.lookup, lambda phrase: registry.non_actor(phrase) is not None)
    reports = _merge_reports(by_source, policies, facts, registry, published_ids, link_status or {}, today,
                             valid_techniques, (matcher, title_sources))
    vulns = _vulns(by_source, policies, reports)
    campaigns = _campaigns(by_source, policies, registry, published_ids, valid_techniques)
    kev = {v["cve"]: v for v in vulns if v["kev_date_added"] is not None}

    payload: dict = {}
    actor_docs: dict[str, dict] = {}
    index: list[dict] = []
    claims: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for p in shown:
        doc, entry = _actor(p, reports, kev, valid_techniques, window_start)
        actor_docs[p.id] = doc
        index.append(entry)
        payload[f"actors/{p.id}.json"] = doc
        claims[p.id].extend(_first_seen(p.members))
    for c in campaigns:
        for actor in c["actors"]:
            if c["first_seen"]:
                claims[actor].append((c["first_seen"], c["source"]))
    index.sort(key=lambda e: (e["name"].casefold(), e["id"]))
    payload["actors/index.json"] = index

    shards: dict[str, list[dict]] = defaultdict(list)
    for r in reports:
        shards[r.published[:4] if r.published else "undated"].append(r.row())
    shards.setdefault("undated", [])
    for key, rows in shards.items():
        rows.sort(key=lambda row: (row["published"] is None, _negated(row["published"] or ""), row["id"]))
        payload[f"reports/{key}.json"] = rows

    # BEGIN reports index (explore page). Built from the finished shard rows so the two cannot differ.
    payload["reports/index.json"] = build_reports_index(
        [row for key, rows in shards.items() for row in rows], kev_cves=kev, built_at=generated_at)
    # END reports index

    sources = _sources(by_source, policies, facts, year)
    health = [{k: row[k] for k in ("name", "last_success", "record_count", "stale")} for row in sources]
    payload["campaigns.json"] = campaigns
    payload["vulns.json"] = vulns
    payload["sources.json"] = sources
    payload["resolution.json"] = _resolution(registry, reports, facts)
    payload["guesses.json"] = guesses.build_guesses(
        registry, [s for b in by_source.values() for s in b.software],
        [r for b in by_source.values() for r in b.reports if r.source == "paper"],
        payload["resolution.json"]["unresolved_names"], list(facts.guess_labels),
        {p.id: _display_name(p.members) for p in shown},
        shown_sources={key for key, policy in policies.items() if policy in _SHOWS_FACTS})
    payload["trends.json"] = trends.compute(
        [{"id": r.id, "published": r.published, "actors": r.actors, "techniques": r.techniques, "cves": r.cves}
         for r in reports if r.trendable],
        documented={a: doc["techniques_documented"] for a, doc in actor_docs.items()},
        vulns=vulns, first_seen_claims=dict(claims), source_health=health, generated_at=generated_at)
    payload["build.json"] = {
        "built_at": generated_at, "version": facts.version,
        "report_years": sorted(int(k) for k in shards if k != "undated"),
        "report_count": sum(len(rows) for rows in shards.values()),
        "recent_since": payload["trends.json"]["window_start"],
        "recent_months": trends.WINDOW_MONTHS}
    payload["NOTICE.md"] = render_notice(year)
    # BEGIN slugs hook: the frozen slug registry was computed inside resolve(), and this only checks
    # that it saw the same visible sources as the policies and publishes it as data/slugs.json.
    payload["slugs.json"] = slugs.document_for_build(registry, policies)
    # END slugs hook
    return payload


# Inputs

def _timestamp(value: str | None) -> str:
    if value is None:
        value = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not isinstance(value, str) or not _GENERATED_AT.fullmatch(value):
        raise ValueError(f"generated_at must be a UTC timestamp like 2026-09-30T04:00:00Z, got {value!r}")
    return value


def _check_policies(policies: Mapping[str, str]) -> dict[str, str]:
    missing = [key for key in SOURCE_ORDER if key not in policies]
    if missing:
        raise ValueError(f"no publish policy for {', '.join(missing)}; the build refuses to guess one")
    bad = {key: policies[key] for key in SOURCE_ORDER if policies[key] not in POLICY_VALUES}
    if bad:
        raise ValueError(f"unknown publish policy {bad}; expected one of {sorted(POLICY_VALUES)}")
    return {key: policies[key] for key in SOURCE_ORDER}


def _bundles_by_source(bundles) -> dict[str, SourceBundle]:
    items = list(bundles.values()) if isinstance(bundles, Mapping) else list(bundles)
    out: dict[str, SourceBundle] = {}
    for bundle in items:
        if bundle.source not in _ORD:
            raise ValueError(f"bundle from unknown source {bundle.source!r}; known sources: {', '.join(SOURCE_ORDER)}")
        if bundle.source in out:
            raise ValueError(f"two bundles for source {bundle.source!r}")
        # The policy is looked up by record.source below, so a record filed under another
        # source's bundle would be published under the wrong policy.
        for record in (*bundle.reports, *bundle.campaigns):
            if record.source != bundle.source:
                raise ValueError(f"{record.source!r} record {record.source_id!r} is in the {bundle.source!r} bundle")
        out[bundle.source] = bundle
    return out


# Small helpers

def _tidy(value) -> str | None:
    """The text with runs of whitespace as one space, or None when nothing is left."""
    if not isinstance(value, str):
        return None
    return " ".join(value.split()) or None


def _negated(text: str) -> tuple:
    # Sorts strings in descending order inside an ascending sort.
    return tuple(-ord(c) for c in text)


def _dedupe(items):
    return list(dict.fromkeys(items))


def _by_source_order(records):
    return sorted(records, key=lambda r: (_ORD[r.source], r.source_id))


# Actors

@dataclass
class _Published:
    resolved: ResolvedActor
    members: list[ActorRecord]

    @property
    def id(self) -> str:
        return self.resolved.id


def _published_actors(registry: Registry, policies: dict[str, str]) -> list[_Published]:
    out = []
    for actor in registry.actors:
        for member in actor.members:
            if member.source not in policies:
                raise ValueError(f"actor record from source {member.source!r}, which has no publish policy")
        members = [m for m in actor.members if policies[m.source] in _SHOWS_FACTS]
        # An actor only evidence-only sources know has nothing publishable, and a page of
        # bare merge counts would say nothing a reader could use.
        if members:
            out.append(_Published(actor, _by_source_order(members)))
    return out


def _sourced(entries) -> list[dict]:
    return [{"value": v, "source": s} for v, s in entries]


def _agree_words(a: str, b: str) -> bool:
    """Motivation wording agrees when the values match or one contains the other as whole words."""
    a, b = a.casefold(), b.casefold()
    return a == b or bool(re.search(rf"(?<!\w){re.escape(a)}(?!\w)", b) or re.search(rf"(?<!\w){re.escape(b)}(?!\w)", a))


def _same_country(a: str, b: str) -> bool:
    ca, cb = iso2(a), iso2(b)
    return ca == cb if ca and cb else a.casefold() == b.casefold()


def _conflict(field_name: str, entries: list[tuple[str, str]], agree) -> list[dict]:
    """A conflict when two sources give values that share nothing, showing every side.

    A source that lists two origins does not conflict with itself, and two sources
    conflict only when none of their values agree.
    """
    values: dict[str, list[str]] = defaultdict(list)
    for value, source in entries:
        values[source].append(value)
    for s1, s2 in combinations(sorted(values, key=_ORD.get), 2):
        if not any(agree(a, b) for a in values[s1] for b in values[s2]):
            return [{"field": field_name, "values": _sourced(entries)}]
    return []


def _aliases(p: _Published, name: str, policies_visible) -> list[dict]:
    sources: dict[str, set[str]] = defaultdict(set)
    for claim in p.resolved.aliases:
        value = _tidy(claim.value)
        # An ATT&CK group ID in an alias list is a cross-reference, not a name.
        if value and not _GROUP_ID.fullmatch(value) and policies_visible(claim.prov.source):
            sources[value].add(claim.prov.source)
    if name not in sources:
        sources[name] = {p.members[0].source}
    order = {value: i for i, value in enumerate(sources)}
    ranked = sorted(sources, key=lambda v: (v != name, -len(sources[v]), order[v]))
    return [{"value": v, "sources": sorted(sources[v], key=_ORD.get)} for v in ranked]


def _actor(p: _Published, reports: list["_Report"], kev: dict[str, dict], valid_techniques,
           window_start: str) -> tuple[dict, dict]:
    members = p.members
    visible_sources = {m.source for m in members}
    name = _display_name(members)

    origin = _dedupe((c, m.source) for m in members for v in m.origin if (c := iso2(v)))
    sponsor = _dedupe((t, m.source) for m in members for v in m.sponsor if (t := _tidy(v)))
    motivation = _dedupe((t, m.source) for m in members for v in m.motivation if (t := _tidy(v)))
    countries = _dedupe((country_name(c), m.source) for m in members for v in m.targets_countries
                        if (c := iso2(v)))
    sectors = _dedupe((t, m.source) for m in members for v in m.targets_sectors
                      if (t := _tidy(v)) and len(t) <= MAX_SECTOR_LENGTH)
    # Malpedia names families it cannot name "unidentified NNN". That is a placeholder, not a malware name.
    malware = _dedupe((t, m.source) for m in members for v in m.malware
                      if (t := _tidy(v)) and not t.casefold().startswith("unidentified"))
    documented = sorted({t for m in members for t in m.techniques if _TECHNIQUE.fullmatch(t)})

    mine = [r for r in reports if p.id in r.actors]
    mine.sort(key=lambda r: (r.published is None, _negated(r.published or ""), r.id))
    quarters = Counter(_quarter(r.published) for r in mine if r.published)
    reported = Counter(t for r in mine if r.trendable and r.published and r.published >= window_start
                       for t in r.techniques)
    cves = sorted({c for r in mine for c in r.cves})

    aliases = _aliases(p, name, lambda source: source in visible_sources)
    doc = {
        "id": p.id,
        "name": name,
        "aliases": aliases,
        "origin": _sourced(origin),
        "sponsor": _sourced(sponsor),
        "motivation": _sourced(motivation),
        "claimed_targets": {"countries": _sourced(countries), "sectors": _sourced(sectors)},
        "malware": [{"name": n, "source": s} for n, s in malware],
        "techniques_documented": documented,
        "techniques_reported": [{"id": t, "count": n} for t, n in sorted(reported.items(), key=lambda kv: (-kv[1], kv[0]))],
        "cves": [{"cve": c, "kev": c in kev, "ransomware": kev[c]["ransomware"] if c in kev else None} for c in cves],
        "timeline": [{"quarter": q, "count": n} for q, n in sorted(quarters.items())],
        "reports": [r.id for r in mine],
        "conflicts": (_conflict("origin", origin, lambda a, b: a == b)
                      + _conflict("sponsor", sponsor, _same_country)
                      + _conflict("motivation", motivation, _agree_words)),
        # Every edge counts, including those from sources that are not shown. The number says
        # how much evidence the merge rests on, and names none of it.
        "evidence_count": len(p.resolved.evidence),
    }
    dates = [r.published for r in mine if r.published]
    entry = {
        "id": p.id,
        "name": name,
        "aliases": [a["value"] for a in aliases],
        "origin": _dedupe(v for v, _ in origin),
        "report_count": len(mine),
        "last_reported": max(dates) if dates else None,
        "sources": sorted(visible_sources, key=_ORD.get),
    }
    return doc, entry


def _quarter(day: str) -> str:
    return f"{day[:4]}-Q{(int(day[5:7]) - 1) // 3 + 1}"


def _first_seen(members: list[ActorRecord]) -> list[tuple[str, str]]:
    out = []
    for m in members:
        for value in m.first_seen:
            value = (value or "").strip()
            if _YEAR_ONLY.fullmatch(value):
                # A bare year says only that the actor was known that year. January 1 with the
                # basis "year" lets trends count it only when the whole year is inside the window.
                out.append((f"{value}-01-01", "year"))
            elif day := parse_date(value):
                out.append((day, m.source))
    return out


# Reports

@dataclass
class _Report:
    id: str
    title: str
    published: str | None
    basis: str
    organisation: str | None
    url: str | None
    url_ok: bool | None
    archive_url: str | None
    actors: list[str]
    actors_from_title: list[str]
    unresolved: list[str]
    cves: list[str]
    techniques: list[str]
    sources: list[str]

    @property
    def trendable(self) -> bool:
        # The paper is a historical layer, and trends promise not to count it. A report the
        # paper shares with a live source is still that live source's report.
        return any(s != "paper" for s in self.sources)

    def row(self) -> dict:
        return {
            "id": self.id, "title": self.title, "published": self.published, "date_basis": self.basis,
            "organisation": self.organisation, "url": self.url, "url_ok": self.url_ok,
            "archive_url": self.archive_url, "actors": sorted(self.actors),
            "actors_from_title": self.actors_from_title, "actor_names_unresolved": self.unresolved, "cves": self.cves, "techniques": self.techniques,
            "sources": self.sources,
        }


def _is_mirror(url: str) -> bool:
    """True for the paper dataset's mirror copies, which are not where a report was published.

    About 1,244 of the paper's download links point at copies: 1,004 in the CyberMonitor
    repository on GitHub and 240 on app.box.com.
    """
    n = norm_url(url)
    return n.startswith(("github.com/cybermonitor/", "raw.githubusercontent.com/cybermonitor/", "app.box.com/"))


def _valid_url(url) -> str | None:
    url = url.strip() if isinstance(url, str) else ""
    return url if _URL.fullmatch(url) else None


def _keys(r: ReportRecord) -> list[tuple]:
    keys = [("src", r.source, r.source_id)]
    if url := _valid_url(r.url):
        keys.append(("url", norm_url(url)))
    sha1 = (r.sha1 or "").strip().lower()
    if _SHA1.fullmatch(sha1):
        keys.append(("sha1", sha1))
    return keys


def _merge_reports(by_source, policies, facts, registry, published_ids, link_status, today, valid_techniques,
                   titled):
    records: list[ReportRecord] = []
    for source in SOURCE_ORDER:
        if policies[source] in _SHOWS_REPORTS and source in by_source:
            records.extend(sorted(by_source[source].reports, key=lambda r: (r.source_id, r.url or "")))

    parent = list(range(len(records)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    owner: dict[tuple, int] = {}
    for i, r in enumerate(records):
        for key in _keys(r):
            if key in owner:
                a, b = find(i), find(owner[key])
                if a != b:
                    parent[max(a, b)] = min(a, b)
            else:
                owner[key] = i
    groups: dict[int, list[ReportRecord]] = defaultdict(list)
    for i, r in enumerate(records):
        groups[find(i)].append(r)

    checked = {norm_url(k): v for k, v in link_status.items() if isinstance(v, bool)}
    malpedia_links = _malpedia_links(facts, policies)
    group_links = _group_links(facts, policies)
    out = []
    for group in groups.values():
        report = _report(group, policies, malpedia_links, group_links, registry, published_ids, checked, today,
                         valid_techniques, titled)
        if report:
            out.append(report)
    return sorted(out, key=lambda r: r.id)


def _malpedia_links(facts: BuildFacts, policies) -> dict[str, list[str]]:
    if policies["malpedia"] not in _SHOWS_FACTS:
        return {}
    links: dict[str, list[str]] = defaultdict(list)
    for url, names in facts.malpedia_report_links.items():
        links[norm_url(url)].extend(names)
    return links


def _group_links(facts: BuildFacts, policies) -> dict[str, set[str]]:
    if policies["attack"] not in _SHOWS_FACTS:
        return {}
    links: dict[str, set[str]] = defaultdict(set)
    for group, urls in facts.group_reference_urls.items():
        for url in urls:
            links[norm_url(url)].add(group)
    return links


def _report(group: list[ReportRecord], policies, malpedia_links, group_links, registry, published_ids, checked,
            today, valid_techniques, titled) -> "_Report | None":
    group = sorted(group, key=lambda r: (_REPORT_PRIORITY.get(r.source, 9), _ORD[r.source], r.source_id))

    urls = _dedupe(u for r in group if (u := _valid_url(r.url)))
    originals = [u for u in urls if not _is_mirror(u)]
    mirrors = [u for u in urls if _is_mirror(u)]
    # A mirror is published as the url only when nothing else is known. It is a copy of the
    # report, not where it appeared, so a publisher URL always takes the url slot.
    url = originals[0] if originals else (mirrors[0] if mirrors else None)
    archives = [a for r in group if (a := _valid_url(r.archive_url))]
    archive = archives[0] if archives else (mirrors[0] if originals and mirrors else None)
    if archive == url:
        archive = None

    titled_by = next(((r, t) for r in group if (t := _tidy(r.title))), None)
    title = titled_by[1] if titled_by else url
    if title is None:
        return None
    sha1s = sorted({s for r in group if _SHA1.fullmatch(s := (r.sha1 or "").strip().lower())})
    if sha1s:
        report_id = sha1s[0]
    else:
        # Whitespace is percent-encoded because a report ID may contain none.
        first = min(group, key=lambda r: (_ORD[r.source], r.source_id))
        report_id = first.source + ":" + _WHITESPACE.sub(lambda m: "%%%02X" % ord(m.group()), first.source_id)

    published, basis = _date(group, today)
    actors, unresolved = _attach(group, urls, policies, malpedia_links, group_links, registry, published_ids)
    matcher, title_sources = titled
    # Only the title the site shows is read, and only when a source that may be read supplied it.
    named = matcher.match(title) & published_ids if titled_by and titled_by[0].source in title_sources else set()
    from_title = sorted(named - set(actors))
    return _Report(
        id=report_id, title=title, published=published, basis=basis,
        organisation=next((o for r in group if (o := _tidy(r.organisation))), None),
        url=url, url_ok=checked.get(norm_url(url)) if url else None, archive_url=archive,
        actors=sorted(set(actors) | named), actors_from_title=from_title, unresolved=unresolved,
        cves=sorted({c for r in group for v in r.cves if _CVE.fullmatch(c := v.strip().upper())}),
        techniques=sorted({t for r in group for t in r.techniques if t in valid_techniques}),
        sources=sorted({r.source for r in group}, key=_ORD.get))


def _date(group: list[ReportRecord], today: str) -> tuple[str | None, str]:
    candidates = []
    for r in group:
        day = parse_date(r.published)
        # A date after the build is a wrong date, and it would put the report in a shard and a
        # quarter that have not happened. Undated is the honest label.
        if day and r.date_basis in _BASIS_RANK and day <= today:
            candidates.append((_BASIS_RANK[r.date_basis], day, r.date_basis))
    if not candidates:
        return None, "unknown"
    _, day, basis = min(candidates)
    return day, basis


def _attach(group, urls, policies, malpedia_links, group_links, registry, published_ids):
    """The actors a report is tagged with, and the names that resolved to no single actor.

    Only three things tag a report: Malpedia's own report links, ATT&CK's group references
    and the paper's actor names. ORKL's tags never do, and a link-only source's names are not
    read at all. A title that names an actor is added later, by _report, and kept separate.
    """
    names: list[str] = []
    actors: set[str] = set()
    for url in urls:
        n = norm_url(url)
        names.extend(malpedia_links.get(n, ()))
        actors.update(g for g in group_links.get(n, ()) if g in published_ids)
    for r in group:
        if r.source != "orkl" and policies[r.source] in _SHOWS_FACTS:
            names.extend(r.actor_names)
    unresolved: set[str] = set()
    for raw in names:
        name = _tidy(raw)
        if not name:
            continue
        found = registry.lookup(name)
        if found is None:
            unresolved.add(name)
        elif found in published_ids:
            # An actor that has no page cannot be linked, and its name is not "unresolved"
            # either, because the registry did resolve it.
            actors.add(found)
    return sorted(actors), sorted(unresolved)


# Campaigns and vulnerabilities

def _campaigns(by_source, policies, registry, published_ids, valid_techniques) -> list[dict]:
    seen: dict[str, dict] = {}
    for source in SOURCE_ORDER:
        if policies[source] not in _SHOWS_FACTS or source not in by_source:
            continue
        for c in sorted(by_source[source].campaigns, key=lambda c: c.source_id):
            name = _tidy(c.name)
            if not name or not _CAMPAIGN_ID.fullmatch(c.source_id) or c.source_id in seen:
                continue
            refs = {a for ref in c.actor_refs if (a := ref if ref in published_ids else registry.lookup(ref))
                    and a in published_ids}
            seen[c.source_id] = {
                "id": c.source_id, "name": name, "first_seen": parse_date(c.first_seen),
                "last_seen": parse_date(c.last_seen), "actors": sorted(refs),
                "techniques": sorted({t for t in c.techniques if t in valid_techniques}), "source": source}
    return [seen[k] for k in sorted(seen)]


# These sources score CVEs that other sources or reports already name. Their catalogues
# cover nearly every CVE ever issued, so they never add a row of their own.
_SCORES_ONLY = frozenset({"epss"})


def _vulns(by_source, policies, reports: list[_Report]) -> list[dict]:
    rows: dict[str, dict] = {}
    for source in SOURCE_ORDER:
        if policies[source] not in _SHOWS_FACTS or source not in by_source or source in _SCORES_ONLY:
            continue
        for v in sorted(by_source[source].vulns, key=lambda v: v.cve):
            cve = v.cve.strip().upper()
            if _CVE.fullmatch(cve) and cve not in rows:
                rows[cve] = _vuln_row(cve, v)
    named: dict[str, list[_Report]] = defaultdict(list)
    for r in reports:
        for cve in r.cves:
            named[cve].append(r)
    for cve in named:
        rows.setdefault(cve, _vuln_row(cve, None))
    for source in _SCORES_ONLY:
        if policies[source] not in _SHOWS_FACTS or source not in by_source:
            continue
        for v in by_source[source].vulns:
            row = rows.get(v.cve.strip().upper())
            if row is not None and row["epss"] is None:
                row["epss"], row["epss_percentile"] = _score(v.epss), _score(v.epss_percentile)
    for cve, row in rows.items():
        row["actors"] = sorted({a for r in named.get(cve, ()) for a in r.actors})
        row["report_count"] = len(named.get(cve, ()))
    return [rows[k] for k in sorted(rows)]


def _vuln_row(cve: str, v: VulnRecord | None) -> dict:
    return {"cve": cve, "kev_date_added": parse_date(v.kev_date_added) if v else None,
            "ransomware": v.ransomware if v else None, "vendor": _tidy(v.vendor) if v else None,
            "product": _tidy(v.product) if v else None, "epss": None, "epss_percentile": None,
            "actors": [], "report_count": 0}


def _score(value: float | None) -> float | None:
    # A score outside 0 to 1 is a broken feed, and it must not reach the contract.
    return round(value, 5) if value is not None and 0 <= value <= 1 else None


# Sources and resolution

def _sources(by_source, policies, facts: BuildFacts, year: str) -> list[dict]:
    rows = []
    for key in SOURCE_ORDER:
        b = by_source.get(key)
        count = sum(len(x) for x in (b.actors, b.reports, b.campaigns, b.vulns, b.software)) if b else 0
        raw = facts.snapshot_dates.get(key)
        if key == "etda":
            # ETDA's snapshot is refetched on every build while its database stopped changing
            # long ago. The database's own change date tells a reader how old the data is.
            raw = facts.etda_last_db_change or raw
        last = parse_date(raw)
        info = SOURCE_INFO[key]
        rows.append({
            "name": key, "last_success": last, "record_count": count,
            "stale": key in facts.fetch_failed or last is None,
            "publish": policies[key], "licence": info.licence, "licence_url": info.licence_url,
            "attribution": source_attribution(key, year)})
    return rows


def _resolution(registry: Registry, reports: list[_Report], facts: BuildFacts) -> dict:
    names = {n for raw in facts.paper_names if (n := _tidy(raw))}
    resolved = sum(1 for n in names if registry.lookup(n) is not None)
    typed = sum(1 for n in names if registry.lookup(n) is None and registry.non_actor(n) is not None)
    counts = Counter(n for r in reports for n in r.unresolved)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_UNRESOLVED_NAMES]
    return {
        "stats": registry.stats(),
        "paper_match": {"names_total": len(names), "resolved": resolved, "typed_non_actor": typed,
                        "match_rate": resolved / len(names) if names else None},
        "ambiguities": [dict(a) for a in registry.ambiguities],
        "unresolved_names": [{"name": n, "count": c, "typed_as": registry.non_actor(n)} for n, c in ranked],
    }
