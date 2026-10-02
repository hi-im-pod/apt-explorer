"""The data contract: every file in data/ matches its JSON Schema, and the files
agree with each other.

The pipeline writes data/ and the site reads it, and different people build the
two at the same time. These tests are where drift between them shows up: a field
one side renamed, a report filed under the wrong year, an actor page the index
does not list, or a source the licence table keeps private turning up on the
site. They run against whatever data/ holds, which is the hand-made sample until
the pipeline writes its first real build.
"""
import copy
import json
import os
import re
from collections import defaultdict
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from aptx.build.contract import NON_JSON_FILES, SCHEMA_DIR, load_schema, schema_for, validator
from aptx.sources.base import publish_policy

ROOT = Path(__file__).resolve().parents[2]
# APTX_DATA points the whole file at another directory, such as a scratch build,
# so a change to the contract can be checked before data/ itself is regenerated.
DATA = Path(os.environ["APTX_DATA"]) if os.environ.get("APTX_DATA") else ROOT / "data"
SOURCES_MD = ROOT / "SOURCES.md"

# The site fetches these by name, so each must exist even when it is empty.
# The year shards are not listed because which years exist depends on the data;
# build.json's report_years names them.
REQUIRED = ["actors/index.json", "reports/index.json", "reports/undated.json", "campaigns.json", "vulns.json",
            "sources.json", "resolution.json", "trends.json", "build.json", "slugs.json", "guesses.json", "terms.json"]

SCHEMA_NAMES = sorted(p.name.removesuffix(".schema.json") for p in SCHEMA_DIR.glob("*.schema.json"))


def _files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# NOTICE.md is left out by name, not by a pattern such as *.md, so any other
# file without a schema still fails test_every_data_file_has_a_schema.
FILES = [rel for rel in _files(DATA) if rel not in NON_JSON_FILES] if DATA.is_dir() else []


def _load(rel: str):
    return json.loads((DATA / rel).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tree() -> dict:
    return {rel: _load(rel) for rel in FILES if schema_for(rel)}


# --- Every file has a schema, and every file matches it -----------------------

def test_data_directory_holds_every_file_the_site_fetches_by_name():
    assert DATA.is_dir(), f"{DATA} is missing"
    assert [rel for rel in REQUIRED if rel not in FILES] == []


def test_every_data_file_has_a_schema():
    # A file with no schema is a file nobody agreed on. The site may not know it
    # exists, or the pipeline may have renamed a file the site still fetches.
    assert [rel for rel in FILES if schema_for(rel) is None] == []


def test_every_schema_governs_a_data_file():
    # A schema that no file uses means a file was renamed or never written.
    used = {schema_for(rel) for rel in FILES}
    assert [name for name in SCHEMA_NAMES if name not in used] == []


def test_committed_slug_registry_agrees_with_the_actor_pages(tree):
    from aptx.build import slugs
    names = {rel[len("actors/"):-len(".json")]: tree[rel]["name"]
             for rel in tree if rel.startswith("actors/") and rel != "actors/index.json"}
    assert slugs.cross_problems(names, tree["slugs.json"]) == []


@pytest.mark.parametrize("rel", FILES)
def test_data_file_matches_its_schema(rel):
    name = schema_for(rel)
    assert name, f"{rel} has no schema"
    errors = sorted(validator(name).iter_errors(_load(rel)), key=lambda e: list(e.absolute_path))
    assert not errors, "\n".join(f"{rel} at /{'/'.join(map(str, e.absolute_path))}: {e.message}"
                                 for e in errors[:10])


def test_schema_mapping_covers_the_published_layout():
    assert schema_for("actors/index.json") == "actors_index"
    assert schema_for("actors/G0007.json") == "actor"
    assert schema_for("reports/2024.json") == schema_for("reports/undated.json") == "reports_shard"
    assert schema_for("reports\\2024.json") == "reports_shard"
    assert schema_for("reports/latest.json") is None
    assert schema_for("reports/24.json") is None
    assert schema_for("README.md") is None


def test_only_the_notice_is_exempt_from_the_schema_check():
    # Each exemption is a file the site gets with no agreed shape, so the list
    # stays as short as the licences allow.
    assert NON_JSON_FILES == {"NOTICE.md"}
    assert (DATA / "NOTICE.md").is_file()


# --- The schemas themselves ----------------------------------------------------

def _walk(node, pointer=""):
    """Yield (json_pointer, node) for every schema object inside a schema."""
    if isinstance(node, dict):
        yield pointer, node
        for key, value in node.items():
            yield from _walk(value, f"{pointer}/{key.replace('~', '~0').replace('/', '~1')}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _walk(value, f"{pointer}/{i}")


@pytest.mark.parametrize("name", SCHEMA_NAMES)
def test_schema_is_draft_2020_12_and_every_object_is_closed(name):
    schema = load_schema(name)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)
    for pointer, node in _walk(schema):
        if node.get("type") != "object":
            continue
        # additionalProperties: false catches an added or misspelled field, and
        # requiring every property catches a dropped one. The pipeline writes
        # null for a missing value rather than leaving the key out, so the site
        # never has to tell undefined from null.
        assert node.get("additionalProperties") is False, f"{name}{pointer} is open"
        assert sorted(node.get("required", [])) == sorted(node.get("properties", {})), \
            f"{name}{pointer} does not require every property"


def test_shared_definitions_are_identical_across_schemas():
    # Each schema is self-contained, so common definitions such as the date
    # pattern are copied into each file. The copies must not drift apart.
    seen: dict[str, tuple[str, dict]] = {}
    for name in SCHEMA_NAMES:
        for key, definition in load_schema(name).get("$defs", {}).items():
            if key in seen:
                first, other = seen[key]
                assert definition == other, f"$defs/{key} differs between {first} and {name}"
            else:
                seen[key] = (name, definition)


# --- The schemas reject the drift they exist to catch ---------------------------

def _report(**changes):
    report = {"id": "0" * 40, "title": "A report", "published": "2024-05-01",
              "date_basis": "orkl-ingest", "organisation": None, "url": "https://example.org/a",
              "url_ok": None, "archive_url": None, "actors": [], "actors_from_title": [], "actors_from_text": [], "actor_names_unresolved": [],
              "cves": [], "techniques": [], "sources": ["orkl"]}
    report.update(changes)
    return report


def _index_entry(**changes):
    entry = {"id": "G0007", "name": "APT28", "aliases": [], "origin": [], "origin_conflict": False, "report_count": 0,
             "last_reported": None, "sources": ["attack"]}
    entry.update(changes)
    return entry


def _actor(**changes):
    actor = {"id": "G0007", "name": "APT28", "aliases": [{"value": "Fancy Bear", "sources": ["attack"]}],
             "origin": [], "sponsor": [], "motivation": [],
             "claimed_targets": {"countries": [], "sectors": []}, "malware": [],
             "techniques_documented": [], "techniques_reported": [], "cves": [], "timeline": [],
             "reports": [], "conflicts": [], "evidence_count": 0, "cluster_only": False}
    actor.update(changes)
    return actor


def _trends(**changes):
    trends = {"window_start": "2024-07-01", "generated_at": "2026-09-28T03:17:00Z",
              "reporting_activity": [], "new_actors": [], "kev_monthly": [], "kev_actor_links": [],
              "reported_vs_documented": [], "source_health": [],
              "notes": {k: "A counting rule." for k in ("reporting_activity", "new_actors", "kev_monthly",
                                                        "kev_actor_links", "reported_vs_documented",
                                                        "source_health")}}
    trends.update(changes)
    return trends


def _source(**changes):
    source = {"name": "kev", "last_success": None, "record_count": 0, "stale": True, "publish": "full",
              "licence": "CC0 1.0",
              "licence_url": "https://www.cisa.gov/sites/default/files/licenses/kev/license.txt",
              "attribution": "CISA Known Exploited Vulnerabilities Catalog, "
                             "https://www.cisa.gov/known-exploited-vulnerabilities-catalog, CC0 1.0."}
    source.update(changes)
    return source


def _without(doc: dict, key: str) -> dict:
    return {k: v for k, v in doc.items() if k != key}


VALID = [
    ("reports_shard", [_report()]),
    ("reports_shard", [_report(published=None, date_basis="unknown")]),
    ("actors_index", [_index_entry()]),
    ("actor", _actor()),
    ("sources", [_source()]),
    ("trends", _trends()),
    ("build", {"built_at": "2026-09-28T03:21:05Z", "version": "0.1.0", "report_years": [], "report_count": 0,
            "recent_since": "2024-01-01", "recent_months": 24}),
]

INVALID = [
    ("reports_shard", [_report(archiveUrl="https://example.org/a.pdf")], "an unknown field"),
    ("reports_shard", [_without(_report(), "title")], "a missing field"),
    ("reports_shard", [_report(published="0001-01-01")], "a year-1 sentinel date"),
    ("reports_shard", [_report(published="2024-05-01T00:00:00Z")], "a timestamp where a date belongs"),
    ("reports_shard", [_report(published=None)], "an undated report whose basis is not 'unknown'"),
    ("reports_shard", [_report(date_basis="unknown")], "a dated report whose basis is 'unknown'"),
    ("reports_shard", [_report(date_basis="guess")], "an unknown date basis"),
    ("reports_shard", [_report(url=None, url_ok=True)], "a link check on a missing URL"),
    ("reports_shard", [_report(id="orkl-123")], "a report ID that is neither a SHA-1 nor source:id"),
    ("reports_shard", [_report(cves=["cve-2023-23397"])], "a lower-case CVE"),
    ("reports_shard", [_report(techniques=["T1059.1"])], "a malformed technique ID"),
    ("reports_shard", [_report(sources=["MITRE ATT&CK"])], "a source name instead of its key"),
    ("reports_shard", [_report(sources=[])], "a report with no source"),
    ("reports_shard", [_report(title=" padded ")], "untrimmed text"),
    ("actors_index", [_index_entry(id="misp:5a1b")], "an actor ID that cannot be a file name"),
    ("actors_index", [_index_entry(id="index")], "an actor ID that would overwrite the index"),
    ("actors_index", [_index_entry(aliases=["Sofacy", "Sofacy"])], "a repeated alias"),
    ("actor", _actor(aliases=[{"value": "Fancy Bear"}]), "a nested object missing a field"),
    ("actor", _actor(timeline=[{"quarter": "2024-Q5", "count": 1}]), "a quarter that does not exist"),
    ("actor", _actor(conflicts=[{"field": "origin", "values": [{"value": "RU", "source": "misp"}]}]),
     "a conflict with one side"),
    ("sources", [_source(publish="public")], "an unknown publish policy"),
    ("sources", [_without(_source(), "attribution")], "a source with no attribution text"),
    ("sources", [_source(attribution="")], "an empty attribution"),
    ("sources", [_source(licence=None)], "a source with no licence named"),
    ("sources", [_source(licence_url=None)], "a source with no licence URL"),
    ("sources", [_source(licence_url="cisa.gov/license.txt")], "a licence URL that is not http or https"),
    ("trends", _trends(notes={"reporting_activity": "A counting rule."}), "a chart without its note"),
    ("build", {"built_at": "2026-09-28T03:21:05Z", "version": "0.1.0"}, "no list of report years"),
]


@pytest.mark.parametrize("name,doc", VALID)
def test_the_rejected_documents_start_from_valid_ones(name, doc):
    # Without this control, a negative case could pass because its base
    # document was already invalid rather than because of the one change.
    assert list(validator(name).iter_errors(doc)) == []


@pytest.mark.parametrize("name,doc,why", INVALID, ids=[why for _, _, why in INVALID])
def test_schema_rejects(name, doc, why):
    assert list(validator(name).iter_errors(doc)), f"{name} accepted {why}"


# --- The files agree with each other ------------------------------------------

def _quarter(date: str) -> str:
    return f"{date[:4]}-Q{(int(date[5:7]) - 1) // 3 + 1}"


def _source_refs(tree: dict):
    """Yield (where, source_key) for every published fact that names its source."""
    for entry in tree.get("actors/index.json", []):
        for key in entry["sources"]:
            yield f"actors/index.json {entry['id']}", key
    for rel, doc in tree.items():
        name = schema_for(rel)
        if name == "actor":
            for alias in doc["aliases"]:
                for key in alias["sources"]:
                    yield f"{rel} aliases", key
            claims = doc["origin"] + doc["sponsor"] + doc["motivation"] + doc["malware"]
            claims += doc["claimed_targets"]["countries"] + doc["claimed_targets"]["sectors"]
            claims += [v for c in doc["conflicts"] for v in c["values"]]
            for claim in claims:
                yield rel, claim["source"]
        elif name == "reports_shard":
            for report in doc:
                for key in report["sources"]:
                    yield f"{rel} {report['id']}", key
    for campaign in tree.get("campaigns.json", []):
        yield f"campaigns.json {campaign['id']}", campaign["source"]
    # A first_seen date is a published fact too. Its basis is a source key
    # unless it came from the earliest dated report.
    for row in tree.get("trends.json", {}).get("new_actors", []):
        if row["basis"] != "report":
            yield f"trends new_actors {row['actor']} basis", row["basis"]


def add_index_problems(tree: dict, reports: dict[str, dict], add) -> None:
    """reports/index.json and the shards must describe the same reports, one for one."""
    index = tree.get("reports/index.json")
    if index is None:
        return
    id_len = index["id_len"]
    keys = {r if not re.fullmatch(r"[0-9a-f]{40}", r) else r[:id_len] for r in reports}
    listed = index["columns"]["id"]
    if index["total"] != len(reports):
        add(f"reports/index.json total {index['total']} but the shards hold {len(reports)} reports")
    for name, column in index["columns"].items():
        if len(column) != index["total"]:
            add(f"reports/index.json columns.{name} has {len(column)} entries, total is {index['total']}")
    if len(set(listed)) != len(listed):
        add("reports/index.json lists an id twice")
    if set(listed) - keys:
        add(f"reports/index.json lists ids that are in no shard: {sorted(set(listed) - keys)[:5]}")
    if keys - set(listed):
        add(f"reports in a shard but not in reports/index.json: {sorted(keys - set(listed))[:5]}")
    if "build.json" in tree and index["built_at"] != tree["build.json"]["built_at"]:
        add("reports/index.json built_at differs from build.json")


def integrity_problems(tree: dict) -> list[str]:
    """Every way the files in `tree` contradict each other, as readable lines."""
    problems: list[str] = []
    add = problems.append

    index = tree.get("actors/index.json", [])
    ids = [entry["id"] for entry in index]
    known = set(ids)
    if len(ids) != len(known):
        add("actors/index.json lists an actor twice")
    pages = {rel.removeprefix("actors/").removesuffix(".json"): doc
             for rel, doc in tree.items() if schema_for(rel) == "actor"}
    # The site prerenders one page per index entry, and a missing file fails
    # the build, so the index and the actor files must match exactly.
    if set(pages) != known:
        add(f"actor files without an index entry: {sorted(set(pages) - known)}; "
            f"index entries without a file: {sorted(known - set(pages))}")
    for stem, page in pages.items():
        if page["id"] != stem:
            add(f"actors/{stem}.json holds actor {page['id']}")

    shards = {rel.removeprefix("reports/").removesuffix(".json"): doc
              for rel, doc in tree.items() if schema_for(rel) == "reports_shard"}
    reports: dict[str, dict] = {}
    for stem, rows in shards.items():
        for report in rows:
            if report["id"] in reports:
                add(f"report {report['id']} appears twice")
            reports[report["id"]] = report
            belongs = report["published"][:4] if report["published"] else "undated"
            if belongs != stem:
                add(f"report {report['id']} published {report['published']} is in reports/{stem}.json")
    add_index_problems(tree, reports, add)
    years = sorted(int(stem) for stem in shards if stem != "undated")
    if "build.json" in tree and tree["build.json"]["report_years"] != years:
        add(f"build.json report_years {tree['build.json']['report_years']} but the shards are {years}")
    if "build.json" in tree and "trends.json" in tree and             tree["build.json"]["recent_since"] != tree["trends.json"]["window_start"]:
        add("build.json recent_since is not trends.json window_start")
    held = sum(len(rows) for rows in shards.values())
    if "build.json" in tree and tree["build.json"]["report_count"] != held:
        add(f"build.json report_count {tree['build.json']['report_count']} but the shards hold {held}")

    def need_actor(where: str, actor_id: str) -> None:
        if actor_id not in known:
            add(f"{where} names actor {actor_id}, which actors/index.json does not list")

    for report in reports.values():
        for actor_id in report["actors"]:
            need_actor(f"report {report['id']}", actor_id)
    for campaign in tree.get("campaigns.json", []):
        for actor_id in campaign["actors"]:
            need_actor(f"campaign {campaign['id']}", actor_id)
    for vuln in tree.get("vulns.json", []):
        for actor_id in vuln["actors"]:
            need_actor(f"vulns.json {vuln['cve']}", actor_id)
    resolution = tree.get("resolution.json")
    if resolution:
        for amb in resolution["ambiguities"]:
            for actor_id in amb["candidates"]:
                need_actor(f"ambiguity {amb['alias']!r}", actor_id)
    trends = tree.get("trends.json")
    if trends:
        for section in ("reporting_activity", "new_actors", "reported_vs_documented"):
            for row in trends[section]:
                need_actor(f"trends {section}", row["actor"])
        for link in trends["kev_actor_links"]:
            for actor_id in link["actors"]:
                need_actor(f"trends kev_actor_links {link['cve']}", actor_id)

    # An actor page, its index row and the report shards must tell one story.
    tagged: dict[str, set[str]] = defaultdict(set)
    for report in reports.values():
        for actor_id in report["actors"]:
            tagged[actor_id].add(report["id"])
    for entry in index:
        page = pages.get(entry["id"])
        if page is None:
            continue
        where = f"actor {entry['id']}"
        if page["name"] != entry["name"] or [a["value"] for a in page["aliases"]] != entry["aliases"]:
            add(f"{where}: the index and the actor page show different names or aliases")
        if entry["origin_conflict"] != any(c["field"] == "origin" for c in page["conflicts"]):
            add(f"{where}: origin_conflict does not match the conflicts on the actor page")
        if entry["report_count"] != len(page["reports"]):
            add(f"{where}: report_count {entry['report_count']} but the page lists {len(page['reports'])}")
        if set(page["reports"]) != tagged[entry["id"]]:
            add(f"{where}: the page's reports differ from the reports tagged with it")
        dated = [reports[r]["published"] for r in page["reports"] if r in reports and reports[r]["published"]]
        if sum(point["count"] for point in page["timeline"]) != len(dated):
            add(f"{where}: the timeline does not count exactly the dated reports")
        if entry["last_reported"] != (max(dated) if dated else None):
            add(f"{where}: last_reported {entry['last_reported']} is not its newest report")
        page_cves = {c["cve"] for c in page["cves"]}
        report_cves = {c for r in page["reports"] if r in reports for c in reports[r]["cves"]}
        if page_cves != report_cves:
            add(f"{where}: CVEs {sorted(page_cves ^ report_cves)} differ from its reports' CVEs")

    # The licence gate. Nothing from an evidence-only source may reach the site,
    # and a source key sources.json does not list is a typo or a new source
    # nobody recorded terms for.
    sources = {s["name"]: s for s in tree.get("sources.json", [])}
    hidden = {name for name, s in sources.items() if s["publish"] == "evidence-only"}
    for where, key in _source_refs(tree):
        if key not in sources:
            add(f"{where} cites source {key!r}, which sources.json does not list")
        elif key in hidden:
            add(f"{where} publishes {key!r}, whose publish policy is evidence-only")

    vulns: dict[str, dict] = {}
    for vuln in tree.get("vulns.json", []):
        if vuln["cve"] in vulns:
            add(f"vulns.json lists {vuln['cve']} twice")
        vulns[vuln["cve"]] = vuln
    by_cve: dict[str, list[dict]] = defaultdict(list)
    for report in reports.values():
        for cve in report["cves"]:
            by_cve[cve].append(report)
    for cve in sorted(set(by_cve) - set(vulns)):
        add(f"{cve} appears in a report but not in vulns.json")
    for cve, vuln in vulns.items():
        rows = by_cve.get(cve, [])
        if vuln["report_count"] != len(rows):
            add(f"vulns.json {cve}: report_count {vuln['report_count']} but {len(rows)} reports name it")
        if sorted(vuln["actors"]) != sorted({a for r in rows for a in r["actors"]}):
            add(f"vulns.json {cve}: actors differ from the actors of the reports that name it")
        if vuln["kev_date_added"] is None and vuln["ransomware"] is not None:
            add(f"vulns.json {cve}: not in KEV, so KEV cannot say anything about ransomware")
    for rel, page in tree.items():
        if schema_for(rel) != "actor":
            continue
        for c in page["cves"]:
            vuln = vulns.get(c["cve"])
            if vuln and (c["kev"] != (vuln["kev_date_added"] is not None) or c["ransomware"] != vuln["ransomware"]):
                add(f"{rel} {c['cve']}: the KEV flags differ from vulns.json")

    if resolution:
        stats, paper = resolution["stats"], resolution["paper_match"]
        if stats["ambiguity_count"] != len(resolution["ambiguities"]):
            add("resolution.json ambiguity_count differs from the ambiguities listed")
        if stats["merge_count"] != stats["source_record_count"] - stats["actor_count"]:
            add("resolution.json merge_count is not source_record_count minus actor_count")
        # The methodology page prints this count next to a list of the actors,
        # so the two must be the same number.
        if stats["actor_count"] != len(index):
            add(f"resolution.json actor_count {stats['actor_count']} but actors/index.json lists {len(index)}")
        if paper["resolved"] + paper["typed_non_actor"] > paper["names_total"]:
            add("resolution.json paper_match counts more names than the paper has")
        rate = paper["resolved"] / paper["names_total"] if paper["names_total"] else None
        if (rate is None) != (paper["match_rate"] is None) or (rate is not None and abs(rate - paper["match_rate"]) > 1e-6):
            add(f"resolution.json match_rate {paper['match_rate']} is not resolved / names_total ({rate})")

    if trends:
        # Trends describe 2024 onward. An earlier bucket means pre-window data
        # leaked into a chart that says it starts at window_start.
        start = trends["window_start"]
        for row in trends["reporting_activity"]:
            if row["quarter"] < _quarter(start):
                add(f"trends reporting_activity has {row['quarter']}, before {start}")
        for row in trends["kev_monthly"]:
            if row["month"] < start[:7]:
                add(f"trends kev_monthly has {row['month']}, before {start}")
            if row["ransomware"] > row["added"]:
                add(f"trends kev_monthly {row['month']}: more ransomware CVEs than CVEs added")
        for link in trends["kev_actor_links"]:
            if vulns.get(link["cve"], {}).get("kev_date_added") is None:
                add(f"trends kev_actor_links {link['cve']} is not a KEV CVE in vulns.json")
        health = sorted(trends["source_health"], key=lambda s: s["name"])
        status = sorted(({k: s[k] for k in ("name", "last_success", "record_count", "stale")}
                         for s in sources.values()), key=lambda s: s["name"])
        if health != status:
            add("trends source_health differs from sources.json")

    return problems


def test_files_agree_with_each_other(tree):
    assert integrity_problems(tree) == []


def _first_dated_report(tree: dict) -> tuple[str, dict]:
    for rel, doc in sorted(tree.items()):
        if schema_for(rel) == "reports_shard" and not rel.endswith("undated.json") and doc:
            return rel, doc[0]
    pytest.skip("data/ has no dated report to move")


def test_integrity_check_finds_a_report_in_the_wrong_year(tree):
    broken = copy.deepcopy(tree)
    rel, report = _first_dated_report(broken)
    broken[rel].remove(report)
    broken["reports/undated.json"].append(report)
    assert any("is in reports/undated.json" in p for p in integrity_problems(broken))


def test_integrity_check_finds_a_report_the_index_does_not_list(tree):
    if "reports/index.json" not in tree:
        pytest.skip("data/ has no reports index yet")
    broken = copy.deepcopy(tree)
    rel, report = _first_dated_report(broken)
    extra = copy.deepcopy(report)
    extra["id"] = "e" * 40
    broken[rel].append(extra)
    problems = integrity_problems(broken)
    assert any("not in reports/index.json" in p for p in problems)
    assert any("total" in p for p in problems)


def test_integrity_check_finds_an_indexed_id_with_no_report(tree):
    if "reports/index.json" not in tree:
        pytest.skip("data/ has no reports index yet")
    broken = copy.deepcopy(tree)
    rel, report = _first_dated_report(broken)
    broken[rel].remove(report)
    assert any("in no shard" in p for p in integrity_problems(broken))


def test_integrity_check_finds_an_actor_count_that_disagrees_with_the_index(tree):
    broken = copy.deepcopy(tree)
    broken["resolution.json"]["stats"]["actor_count"] += 1
    broken["resolution.json"]["stats"]["merge_count"] -= 1
    assert any("actors/index.json lists" in p for p in integrity_problems(broken))


def test_integrity_check_finds_an_actor_page_listing_an_unknown_report(tree):
    broken = copy.deepcopy(tree)
    page = next(doc for rel, doc in broken.items() if schema_for(rel) == "actor")
    page["reports"].append("orkl:no-such-report")
    assert any("differ from the reports tagged" in p for p in integrity_problems(broken))


def test_integrity_check_finds_an_evidence_only_source_on_the_site(tree):
    broken = copy.deepcopy(tree)
    _, report = _first_dated_report(broken)
    source = next(s for s in broken["sources.json"] if s["name"] == report["sources"][0])
    source["publish"] = "evidence-only"
    assert any("evidence-only" in p for p in integrity_problems(broken))


def test_integrity_check_finds_a_first_seen_date_from_an_evidence_only_source(tree):
    broken = copy.deepcopy(tree)
    if not broken["trends.json"]["new_actors"]:
        pytest.skip("data/ has no newly documented actor")
    source = broken["sources.json"][0]
    source["publish"] = "evidence-only"
    broken["trends.json"]["new_actors"][0]["basis"] = source["name"]
    assert any("new_actors" in p and "evidence-only" in p for p in integrity_problems(broken))


# --- sources.json and NOTICE.md say what SOURCES.md says --------------------------

_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
_QUOTED = re.compile(r'"([^"]+)"')


def _licence_table() -> dict[str, dict[str, str]]:
    """SOURCES.md's licence table as {connector key: {column header: cell}}.

    A row belongs to the key its first cell names in backticks, as in
    "MITRE ATT&CK® (`attack`)", which is the same rule publish_policy() uses.
    """
    rows: dict[str, dict[str, str]] = {}
    header: list[str] | None = None
    for line in SOURCES_MD.read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith("|"):
            header = None
            continue
        cells = [c.strip().replace("\\|", "|") for c in _UNESCAPED_PIPE.split(line.strip().strip("|"))]
        if header is None:
            header = cells
            continue
        key = re.search(r"\(`([a-z][a-z0-9-]*)`\)", cells[0])
        if key:
            rows[key.group(1)] = dict(zip(header, cells))
    return rows


def _column(row: dict[str, str], prefix: str) -> str:
    return next(cell for header, cell in row.items() if header.startswith(prefix))


def _attribution(key: str, row: dict[str, str]) -> str:
    """The attribution text for one source: the strings its SOURCES.md row
    quotes in the Attribution column, in order, joined by single spaces."""
    quotes = _QUOTED.findall(_column(row, "Attribution"))
    if key == "attack":
        # The cell says the copyright designation is "followed by the licence
        # paragraph quoted in the previous column" and then the trademark line.
        # MITRE's licence only holds if that paragraph travels with every copy.
        quotes.insert(1, _QUOTED.findall(_column(row, "Licence"))[0])
    if key == "kev":
        # The second quote is the licence's condition about the CISA logo and
        # DHS seal. The site follows it, but it is not credit text.
        quotes = quotes[:1]
    return " ".join(quotes)


@pytest.fixture(scope="module")
def licence_table() -> dict[str, dict[str, str]]:
    table = _licence_table()
    assert len(table) == 13, f"SOURCES.md rows found for {sorted(table)}"
    return table


def test_sources_json_lists_every_source_in_the_licence_table(tree, licence_table):
    assert sorted(s["name"] for s in tree["sources.json"]) == sorted(licence_table)


def test_publish_values_are_the_ones_sources_md_sets(tree):
    # The site hides or shows data by the publish value in sources.json. If it
    # drifted from SOURCES.md, the site would apply a licence decision nobody
    # made. publish_policy() is the reader the pipeline uses, so the sample and
    # real builds are held to the same parse.
    wrong = {s["name"]: (s["publish"], publish_policy(s["name"], SOURCES_MD)) for s in tree["sources.json"]
             if s["publish"] != publish_policy(s["name"], SOURCES_MD)}
    assert wrong == {}, "name: (sources.json, SOURCES.md)"


def test_attribution_is_the_text_sources_md_gives(tree, licence_table):
    for source in tree["sources.json"]:
        expected = _attribution(source["name"], licence_table[source["name"]])
        assert source["attribution"] == expected, source["name"]


def test_licence_url_is_one_sources_md_records_for_that_source(tree, licence_table):
    # A licence link the audit never read could point at the wrong terms.
    for source in tree["sources.json"]:
        row = " ".join(licence_table[source["name"]].values())
        assert source["licence_url"] in row, source["name"]


def test_attribution_helper_rebuilds_the_mitre_notice_in_order(licence_table):
    text = _attribution("attack", licence_table["attack"])
    assert re.match(r"© [0-9]{4} The MITRE Corporation\. This work is reproduced", text)
    assert "hereby grants you a non-exclusive, royalty-free license" in text
    assert text.endswith("MITRE ATT&CK® and ATT&CK® are registered trademarks of The MITRE Corporation.")
    assert "CISA Logo" not in _attribution("kev", licence_table["kev"])


def test_notice_carries_the_data_licence_and_every_attribution(tree, licence_table):
    text = (DATA / "NOTICE.md").read_text(encoding="utf-8")
    flat = " ".join(text.split())
    assert "CC BY-NC-SA 4.0" in text
    assert "https://creativecommons.org/licenses/by-nc-sa/4.0/" in text
    # MITRE's licence requires its copyright designation and "this license" in
    # any copy, so each quoted piece must appear verbatim, © and ® included.
    for piece in _QUOTED.findall(_column(licence_table["attack"], "Attribution")) + \
            _QUOTED.findall(_column(licence_table["attack"], "Licence"))[:1]:
        assert piece in text
    for source in tree["sources.json"]:
        assert " ".join(source["attribution"].split()) in flat, source["name"]
    # Section 3(b)(3) of CC BY-NC-SA 4.0 forbids adding terms to adapted
    # material, so the notice says none are added.
    assert re.search(r"no additional terms", flat, re.I)


# --- The sample covers what the site is built against ----------------------------

def test_sample_covers_the_cases_the_site_is_built_against(tree):
    # Wave 1 builds the site against the hand-made sample, so it must contain
    # every awkward case the site has to render. Real pipeline output is not
    # held to this list, because a real week may have no stale source.
    if "sample" not in tree["build.json"]["version"]:
        pytest.skip("data/ is pipeline output, not the hand-made sample")
    index = tree["actors/index.json"]
    pages = [doc for rel, doc in tree.items() if schema_for(rel) == "actor"]
    shards = {rel: doc for rel, doc in tree.items() if schema_for(rel) == "reports_shard"}
    reports = [r for rows in shards.values() for r in rows]

    assert len(index) >= 12
    assert any(a["report_count"] == 0 for a in index), "an actor with zero reports"
    busiest = max(index, key=lambda a: a["report_count"])
    assert busiest["id"] == "G0032", "Lazarus Group is the actor with the most reports"
    assert any(not re.fullmatch(r"G[0-9]{4}", a["id"]) for a in index), "an actor ATT&CK does not track"
    assert any(len(alias) > 60 and not re.search(r"\s", alias) for a in index for alias in a["aliases"]), \
        "an alias over 60 characters with no spaces"
    assert any(c["field"] == "origin" and len({v["source"] for v in c["values"]}) >= 2
               for page in pages for c in page["conflicts"]), "an origin conflict between two sources"
    assert {"alias": "winnti", "candidates": ["G0044", "G0096"]} in tree["resolution.json"]["ambiguities"]

    assert {f"reports/{y}.json" for y in (2023, 2024, 2025, 2026)} <= set(shards)
    assert tree["reports/undated.json"], "at least one undated report"
    assert {r["date_basis"] for r in reports} == {"malpedia-library", "file-metadata", "orkl-ingest",
                                                  "publisher", "paper", "unknown"}
    assert {r["url_ok"] for r in reports} == {True, False, None}
    assert any(r["url"] is None for r in reports) and any(r["archive_url"] is None for r in reports)
    assert any(re.fullmatch(r"[0-9a-f]{40}", r["id"]) for r in reports)
    assert any(":" in r["id"] for r in reports)
    assert any(r["actor_names_unresolved"] and not r["actors"] for r in reports)

    assert any(v["kev_date_added"] and v["ransomware"] is True for v in tree["vulns.json"])
    assert any(v["kev_date_added"] is None for v in tree["vulns.json"]), "a CVE not in KEV"
    assert any(c["source"] == "attack" for c in tree["campaigns.json"]), "an ATT&CK campaign"
    assert any(s["stale"] for s in tree["sources.json"]), "a stale source"
    trends = tree["trends.json"]
    assert all(trends[k] for k in ("reporting_activity", "new_actors", "kev_monthly", "kev_actor_links",
                                   "reported_vs_documented", "source_health")), "a full trends.json"


def test_published_text_is_utf_8_without_mojibake():
    # The About page prints the attribution strings verbatim. A file read as
    # Windows-1252 and saved again turns (R) and (C) into two-character junk,
    # so this reads bytes and never trusts a console print.
    for path in sorted(DATA.rglob("*")):
        if path.suffix not in {".json", ".md"}:
            continue
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), f"{path.name} starts with a byte order mark"
        text = raw.decode("utf-8")
        # Report titles are published exactly as the sources give them, and one ORKL title
        # already arrives with a U+FFFD where an apostrophe was lost upstream. Repairing it
        # would mean guessing the character, so the replacement-character check skips the
        # report shards and still guards every file this project writes its own text into.
        junk_marks = ("\u00c2\u00ae", "\u00c2\u00a9", "\u00c3", "\u00e2\u20ac")
        if path.parent.name != "reports":
            junk_marks += ("\ufffd",)
        for junk in junk_marks:
            assert junk not in text, f"{path.relative_to(DATA)} contains {junk!r}, which is mojibake"


def test_no_published_title_starts_with_its_filing_date(tree):
    # VX-Underground files papers as "2014-11-14 - Title". The pipeline moves that date into
    # published and drops it from the title, so a prefix left in a shard means a file skipped
    # the split and the Explore table would show the date twice.
    prefix = re.compile(r"^\d{4}-\d{2}-\d{2}\s+[-–—]\s")
    shards = {rel: rows for rel, rows in tree.items() if rel.startswith("reports/") and rel != "reports/index.json"}
    assert shards, "no report shards to check"
    left = [r["title"] for rows in shards.values() for r in rows if prefix.match(r["title"])]
    assert not left, f"{len(left)} titles still start with a date, for example {left[:3]}"
