"""Freeze one built data/ tree as a citable release: validate it, fingerprint it, describe it.

    python -m aptx.freeze --data ../data --version v1.0.0 --commit <sha> [--run <id>] --out ../releases/v1.0.0

The weekly build deploys data/ without committing it, and a later build from newer snapshots
gives different data. A thesis or paper therefore cites one frozen build, never the live site.
This writes two files to --out:

- SHA256SUMS, one line per data file in the format `sha256sum -c` reads from the repository root;
- MANIFEST.json, with the version, the commit and workflow run that built the data, the build
  time, the SHA-256 of every file, and the composition counts the datasheet quotes.

The tree is checked with the same rules the pipeline applies before it writes data/, so a tree
that the site would refuse cannot be frozen. Nothing here reads the clock, so freezing the same
tree twice gives byte-identical files.
"""
import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

from aptx.build import write

_VERSION = re.compile(r"v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")
_COMMIT = re.compile(r"[0-9a-f]{40}")


def _files(data: Path) -> list[Path]:
    # Sorted by the relative path as text, so the order is the same on every operating system.
    # Windows compares Path objects without regard to case, which would put NOTICE.md after actors/.
    return sorted((p for p in data.rglob("*") if p.is_file()), key=lambda p: p.relative_to(data).as_posix())


def load_tree(data: Path) -> dict:
    """The data/ tree as the payload write.validate() checks: parsed JSON, and NOTICE.md as text."""
    payload: dict = {}
    for path in _files(data):
        rel = path.relative_to(data).as_posix()
        text = path.read_bytes().decode("utf-8")
        payload[rel] = text if rel.endswith(".md") else json.loads(text)
    return payload


def file_hashes(data: Path) -> list[dict]:
    out = []
    for path in _files(data):
        blob = path.read_bytes()
        out.append({"path": path.relative_to(data).as_posix(), "bytes": len(blob),
                    "sha256": hashlib.sha256(blob).hexdigest()})
    return out


def composition(payload: dict) -> dict:
    """The counts a datasheet needs, read from the tree itself so they cannot drift from it."""
    reports = [r for rel, rows in payload.items()
               if rel.startswith("reports/") and rel != "reports/index.json" for r in rows]
    trends = payload["trends.json"]

    def has(field):
        return sum(bool(r[field]) for r in reports)

    return {
        "reports": len(reports),
        "reports_by_source": dict(sorted(Counter(s for r in reports for s in r["sources"]).items())),
        "reports_by_date_basis": dict(Counter(r["date_basis"] for r in reports).most_common()),
        "reports_undated": sum(r["published"] is None for r in reports),
        "reports_with_publisher": has("organisation"),
        "reports_with_actor": has("actors"),
        "reports_with_actor_from_title": has("actors_from_title"),
        "reports_with_actor_from_text": has("actors_from_text"),
        "reports_with_cve": has("cves"),
        "reports_with_technique": has("techniques"),
        "reports_with_technique_from_paper": sum(bool(r["techniques"]) and "paper" in r["sources"] for r in reports),
        "reports_with_100_or_more_techniques": sum(len(r["techniques"]) >= 100 for r in reports),
        "reports_with_15_or_more_actors": sum(len(r["actors"]) >= 15 for r in reports),
        "reports_merged_from_copies": sum(bool(r["merged_ids"]) for r in reports),
        "merged_ids": sum(len(r["merged_ids"]) for r in reports),
        "url_checked": sum(r["url_ok"] is not None for r in reports),
        "url_failed": sum(r["url_ok"] is False for r in reports),
        "actors": len(payload["actors/index.json"]),
        "actors_cluster_only": sum(bool(payload.get(f"actors/{a['id']}.json", {}).get("cluster_only"))
                                   for a in payload["actors/index.json"]),
        "campaigns": len(payload["campaigns.json"]),
        "vulnerabilities": len(payload["vulns.json"]),
        "trend_window_start": trends["window_start"],
        "trend_reports_left_out_for_many_actors": trends["many_actor_reports"]["reports"],
        "new_actors": len(trends["new_actors"]),
        "sources": [{"name": s["name"], "publish": s["publish"], "last_success": s["last_success"],
                     "record_count": s["record_count"], "stale": s["stale"]} for s in payload["sources.json"]],
    }


def freeze(data: Path, version: str, commit: str, run: str | None = None) -> tuple[dict, str]:
    """The manifest and the SHA256SUMS text for the tree at `data`, or ValueError if it is not frozen-worthy."""
    if not _VERSION.fullmatch(version):
        raise ValueError(f"version must look like v1.0.0, got {version!r}")
    if not _COMMIT.fullmatch(commit):
        raise ValueError(f"commit must be a full 40-character SHA, got {commit!r}")
    payload = load_tree(data)
    write.validate(payload)
    files = file_hashes(data)
    manifest = {
        "version": version,
        "data_built_at": payload["build.json"]["built_at"],
        "source_commit": commit,
        "workflow_run": run,
        "data_license": "CC-BY-NC-SA-4.0",
        "code_license": "MIT",
        "composition": composition(payload),
        "files": files,
    }
    prefix = data.name
    sums = "".join(f"{f['sha256']}  {prefix}/{f['path']}\n" for f in files)
    return manifest, sums


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=Path("../data"))
    ap.add_argument("--version", required=True)
    ap.add_argument("--commit", required=True, help="the full SHA of the commit whose workflow built the data")
    ap.add_argument("--run", default=None, help="the GitHub Actions run ID that built the data")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    try:
        manifest, sums = freeze(a.data, a.version, a.commit, a.run)
    except (ValueError, write.WriteRefused) as e:
        print(f"not frozen: {e}", file=sys.stderr)
        return 1
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                                         encoding="utf-8", newline="\n")
    (a.out / "SHA256SUMS").write_text(sums, encoding="utf-8", newline="\n")
    print(f"frozen {len(manifest['files'])} files, {manifest['composition']['reports']} reports, into {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
