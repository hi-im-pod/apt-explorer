"""Write data/ from an assembled payload, or refuse and leave data/ as it is.

The site reads data/ and nothing else, so a half-written or self-contradicting
data/ is worse than last build's data/. write_all therefore checks the whole
payload first, writes the files into a directory next to the target, and only
then swaps that directory into place. Any problem found before the swap leaves
the target directory byte for byte as it was.

The payload is a flat dict from a path relative to data/ ("actors/G0007.json",
"trends.json") to the JSON value for that file, plus "NOTICE.md" mapped to its
text. assemble.assemble() returns exactly this.
"""
import json
import os
import re
import shutil
from pathlib import Path

from aptx.build import slugs
from aptx.build.contract import NON_JSON_FILES, load_schema, schema_for, validator
from aptx.build.report_index import build_reports_index, short_id

# Files that must exist for the site to load at all. Year shards and actor
# pages are not listed because how many there are depends on the data, but the
# undated shard is always there, even when empty, so the site can fetch it
# without first checking whether it exists.
REQUIRED = ("actors/index.json", "reports/index.json", "reports/undated.json", "campaigns.json", "vulns.json",
            "sources.json", "resolution.json", "trends.json", "build.json", "slugs.json", "guesses.json",
            "NOTICE.md")

_ACTOR_FILE = re.compile(r"actors/([^/]+)\.json")
_SHARD = re.compile(r"reports/([0-9]{4}|undated)\.json")
_MAX_PER_FILE = 5


class WriteRefused(ValueError):
    """The payload broke the contract, so nothing was written. `problems` lists every reason."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(f"refusing to write data/, {len(problems)} problem(s):\n  " + "\n  ".join(problems))


def _rename(src: Path, dst: Path) -> None:
    # A separate function so a test can make one move fail.
    os.rename(src, dst)


def _actor_id_pattern() -> re.Pattern[str]:
    # Read from the schema so a change to the ID rules cannot leave the file-name check behind.
    return re.compile(load_schema("actor")["$defs"]["actorId"]["pattern"])


def _serialize(payload: dict) -> tuple[dict[str, str], list[str]]:
    """The text of every file, and the reasons any could not be produced."""
    texts: dict[str, str] = {}
    problems: list[str] = []
    for rel in sorted(payload):
        value = payload[rel]
        if not isinstance(rel, str) or not rel or rel.startswith("/") or "\\" in rel \
                or any(part in ("", ".", "..") for part in rel.split("/")):
            problems.append(f"{rel!r}: not a plain path relative to data/")
            continue
        if rel in NON_JSON_FILES:
            if not isinstance(value, str):
                problems.append(f"{rel}: must be text, got {type(value).__name__}")
            else:
                texts[rel] = value if value.endswith("\n") else value + "\n"
            continue
        name = schema_for(rel)
        stem = _ACTOR_FILE.fullmatch(rel)
        if name is None or (stem and name == "actor" and not _actor_id_pattern().fullmatch(stem.group(1))):
            problems.append(f"{rel}: no schema governs this path, so it cannot be published")
            continue
        try:
            # allow_nan=False because NaN is not JSON, and a browser's JSON.parse would reject the file.
            texts[rel] = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
        except (TypeError, ValueError) as e:
            problems.append(f"{rel}: cannot be written as JSON ({e})")
    return texts, problems


def _schema_problems(texts: dict[str, str]) -> tuple[dict[str, object], list[str]]:
    """Validate what will be on disk, not the in-memory object, so a tuple or other
    quirk that changes in serialization cannot slip past."""
    parsed: dict[str, object] = {}
    problems: list[str] = []
    for rel, text in texts.items():
        if rel in NON_JSON_FILES:
            continue
        value = json.loads(text)
        parsed[rel] = value
        errors = sorted(validator(schema_for(rel)).iter_errors(value),
                        key=lambda e: [str(p) for p in e.absolute_path])
        for e in errors[:_MAX_PER_FILE]:
            where = "/".join(str(p) for p in e.absolute_path) or "(whole file)"
            problems.append(f"{rel}: {where}: {e.message[:200]}")
        if len(errors) > _MAX_PER_FILE:
            problems.append(f"{rel}: and {len(errors) - _MAX_PER_FILE} more schema problems")
    return parsed, problems


def _notice_problems(text: str) -> list[str]:
    # data/NOTICE.md is the copy of the licence terms that travels with every copy of the
    # files, so a notice without them would defeat its purpose.
    problems = []
    if "CC BY-NC-SA 4.0" not in text:
        problems.append("NOTICE.md: does not state the CC BY-NC-SA 4.0 licence the data is offered under")
    if "The MITRE Corporation" not in text:
        problems.append("NOTICE.md: does not carry MITRE's copyright designation")
    return problems


def _index_problems(parsed: dict[str, object], report_ids: dict[str, str]) -> list[str]:
    """Contradictions between reports/index.json and the report shards it summarises.

    The index is derived data, so the strongest check is to derive it again from
    the shards and demand the same file. The checks before that only explain the
    common failures in words, so a failed build says what is wrong.
    """
    rel = "reports/index.json"
    index = parsed[rel]
    shard_reports = [r for name in sorted(parsed) if _SHARD.fullmatch(name) for r in parsed[name]]
    if len(report_ids) != len(shard_reports):
        return []  # A repeated id is already reported, and the index cannot be rebuilt from it.
    problems: list[str] = []
    built_at = parsed["build.json"]["built_at"]
    if index["built_at"] != built_at:
        problems.append(f"{rel}: built_at is {index['built_at']}, but build.json says {built_at}")
    if index["total"] != len(shard_reports):
        problems.append(f"{rel}: total is {index['total']}, but the report shards hold {len(shard_reports)} reports")
    short = [f"{rel}: columns.{name} has {len(column)} entries, total says {index['total']}"
             for name, column in index["columns"].items() if len(column) != index["total"]]
    if short:
        return problems + short

    id_len = index["id_len"]
    indexed = set(index["columns"]["id"])
    in_shards = {short_id(i, id_len) for i in report_ids}
    for missing in sorted(in_shards - indexed)[:_MAX_PER_FILE]:
        problems.append(f"{rel}: report {missing} is in a report shard but not in the index")
    for extra in sorted(indexed - in_shards)[:_MAX_PER_FILE]:
        problems.append(f"{rel}: {extra} is indexed but is in no report shard")
    if problems:
        return problems  # The rebuild below would only repeat the same news less clearly.

    kev = {v["cve"] for v in parsed["vulns.json"] if v["kev_date_added"] is not None}
    expected = build_reports_index(shard_reports, kev_cves=kev, built_at=built_at)
    if expected != index:
        first = next((k for k in expected if expected[k] != index.get(k)), "?")
        if first in ("tables", "columns"):
            first += "." + next(k for k in expected[first] if expected[first][k] != index[first][k])
        problems.append(f"{rel}: differs from the index rebuilt from the report shards, first at {first}")
    return problems


def _cross_problems(parsed: dict[str, object]) -> list[str]:
    """Contradictions between files that each pass their own schema."""
    problems: list[str] = []
    actor_files = {m.group(1): parsed[rel] for rel in parsed if (m := _ACTOR_FILE.fullmatch(rel)) and rel != "actors/index.json"}
    index = {e["id"]: e for e in parsed["actors/index.json"]}
    known = set(actor_files)

    for actor_id, actor in sorted(actor_files.items()):
        if actor["id"] != actor_id:
            problems.append(f"actors/{actor_id}.json: id is {actor['id']!r}, which is not the file name")
    for actor_id in sorted(known - set(index)):
        problems.append(f"actors/index.json: {actor_id} has an actor file but no index entry")
    for actor_id in sorted(set(index) - known):
        problems.append(f"actors/index.json: {actor_id} is listed but has no actor file")
    for actor_id in sorted(known & set(index)):
        if actor_files[actor_id]["name"] != index[actor_id]["name"]:
            problems.append(f"actors/index.json: {actor_id} is named {index[actor_id]['name']!r} there but "
                            f"{actor_files[actor_id]['name']!r} in its own file")

    # Slugs: every actor page has a frozen slug entry and every live entry has a page.
    problems += slugs.cross_problems({i: a["name"] for i, a in actor_files.items()}, parsed["slugs.json"])

    # Reports: each shard holds one year, and ids are unique across shards.
    report_ids: dict[str, str] = {}
    years: list[int] = []
    for rel in sorted(parsed):
        m = _SHARD.fullmatch(rel)
        if not m:
            continue
        if m.group(1) != "undated":
            years.append(int(m.group(1)))
        for report in parsed[rel]:
            published = report["published"]
            home = "undated" if published is None else published[:4]
            if home != m.group(1):
                problems.append(f"{rel}: report {report['id']} is dated {published}, so it belongs in "
                                f"reports/{home}.json, not {rel}")
            if report["id"] in report_ids:
                problems.append(f"{rel}: report {report['id']} appears more than once "
                                f"(also in {report_ids[report['id']]})")
            report_ids[report["id"]] = rel
            for actor in report["actors"]:
                if actor not in known:
                    problems.append(f"{rel}: report {report['id']} names actor {actor}, which has no actor file")

    if sorted(parsed["build.json"]["report_years"]) != sorted(years):
        problems.append(f"build.json: report_years {parsed['build.json']['report_years']} does not match "
                        f"the report shards written {sorted(years)}")

    problems += _index_problems(parsed, report_ids)

    for actor_id, actor in sorted(actor_files.items()):
        for rid in actor["reports"]:
            if rid not in report_ids:
                problems.append(f"actors/{actor_id}.json: lists report {rid}, which is in no report shard")

    def refs(rel: str, ids) -> None:
        for actor in ids:
            if actor not in known:
                problems.append(f"{rel}: names actor {actor}, which has no actor file")

    refs("campaigns.json", (a for c in parsed["campaigns.json"] for a in c["actors"]))
    refs("vulns.json", (a for v in parsed["vulns.json"] for a in v["actors"]))
    trends = parsed["trends.json"]
    refs("trends.json", (row["actor"] for key in ("reporting_activity", "new_actors", "reported_vs_documented")
                         for row in trends[key]))
    refs("trends.json", (a for row in trends["kev_actor_links"] for a in row["actors"]))
    return sorted(set(problems))


def validate(payload: dict) -> None:
    """Raise WriteRefused unless the payload is a complete, consistent data/ tree."""
    texts, problems = _serialize(payload)
    problems += [f"{rel}: is missing" for rel in REQUIRED if rel not in payload]
    parsed, more = _schema_problems(texts)
    problems += more
    if "NOTICE.md" in texts:
        problems += _notice_problems(texts["NOTICE.md"])
    if not problems:
        problems = _cross_problems(parsed)
    if problems:
        raise WriteRefused(problems)


def write_all(out: Path | str, payload: dict) -> list[str]:
    """Write the payload as the directory `out`, or raise WriteRefused and change nothing.

    Every file is validated against its schema, the cross-file rules hold, and only then
    are the files written to a sibling directory that replaces `out` in one rename. If the
    swap itself fails, the previous `out` is put back. Returns the sorted relative paths
    written. The payload is not modified.
    """
    validate(payload)
    out = Path(out)
    texts, _ = _serialize(payload)

    out.parent.mkdir(parents=True, exist_ok=True)
    new = out.parent / f".{out.name}.new"
    old = out.parent / f".{out.name}.old"
    # A crashed earlier run may have left either directory behind. Neither holds anything
    # worth keeping: `new` was never swapped in, and `old` was already replaced.
    for stale in (new, old):
        shutil.rmtree(stale, ignore_errors=True)
    try:
        for rel, text in texts.items():
            target = new / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            # Bytes, not text mode, so Windows does not turn the line feeds into CRLF.
            target.write_bytes(text.encode("utf-8"))
        if out.exists():
            _rename(out, old)
            try:
                _rename(new, out)
            except BaseException:
                _rename(old, out)
                raise
            shutil.rmtree(old, ignore_errors=True)
        else:
            _rename(new, out)
    finally:
        shutil.rmtree(new, ignore_errors=True)
    return sorted(texts)
