import copy
import json
from pathlib import Path

import pytest

from aptx.build import write as write_module
from aptx.build.contract import NON_JSON_FILES, schema_for
from aptx.build.notice import render_notice
from aptx.build.report_index import build_reports_index
from aptx.build.write import WriteRefused, write_all

# A small, complete and valid tree kept under fixtures/ is the payload every test starts
# from and then breaks in one place. It is not the published data/, because that now holds
# the full live build and these tests write the whole tree dozens of times.
SAMPLE = Path(__file__).resolve().parent / "fixtures" / "sample_data"


def sample_payload() -> dict:
    payload = {}
    for path in sorted(SAMPLE.rglob("*.json")):
        payload[path.relative_to(SAMPLE).as_posix()] = json.loads(path.read_text(encoding="utf-8"))
    payload["NOTICE.md"] = render_notice("2026")
    return payload


def reindex(payload: dict) -> None:
    """Rebuild the index after a test changes a report, as the real build would."""
    reports = [r for rel, rows in payload.items() if rel.startswith("reports/") and rel != "reports/index.json"
               for r in rows]
    kev = {v["cve"] for v in payload["vulns.json"] if v["kev_date_added"] is not None}
    payload["reports/index.json"] = build_reports_index(reports, kev_cves=kev, built_at=payload["build.json"]["built_at"])


def snapshot(directory: Path) -> dict[str, bytes]:
    return {p.relative_to(directory).as_posix(): p.read_bytes()
            for p in sorted(directory.rglob("*")) if p.is_file()}


def refused(tmp_path, payload, match=None):
    """Write into an out directory that already holds a file, and check nothing changed."""
    out = tmp_path / "data"
    out.mkdir()
    (out / "keep.txt").write_text("previous build", encoding="utf-8")
    before = snapshot(out)
    with pytest.raises(WriteRefused, match=match) as info:
        write_all(out, payload)
    assert snapshot(out) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data"], "a temporary directory was left behind"
    return info.value


def test_the_sample_tree_is_a_valid_payload(tmp_path):
    written = write_all(tmp_path / "data", sample_payload())
    assert "actors/G0007.json" in written and "NOTICE.md" in written


def test_every_file_is_written_as_the_payload_says(tmp_path):
    payload = sample_payload()
    out = tmp_path / "data"
    written = write_all(out, payload)
    assert written == sorted(payload)
    for rel, value in payload.items():
        text = (out / rel).read_bytes().decode("utf-8")
        assert (text == value) if rel in NON_JSON_FILES else (json.loads(text) == value)
    assert sorted(snapshot(out)) == sorted(payload)


def test_files_are_stable_utf8_with_lf_line_ends(tmp_path):
    payload = sample_payload()
    payload["reports/2024.json"][0]["title"] = "Ein Bericht über Räuber"
    reindex(payload)
    write_all(tmp_path / "a", payload)
    write_all(tmp_path / "b", payload)
    assert snapshot(tmp_path / "a") == snapshot(tmp_path / "b")
    raw = (tmp_path / "a" / "reports" / "2024.json").read_bytes()
    assert "über Räuber".encode("utf-8") in raw
    for rel, data in snapshot(tmp_path / "a").items():
        assert b"\r" not in data and data.endswith(b"\n"), rel


def test_the_payload_is_not_modified():
    payload = sample_payload()
    before = copy.deepcopy(payload)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        write_all(Path(tmp) / "data", payload)
    assert payload == before


def test_parent_directories_are_created(tmp_path):
    write_all(tmp_path / "deep" / "er" / "data", sample_payload())
    assert (tmp_path / "deep" / "er" / "data" / "build.json").is_file()


def test_a_successful_write_replaces_the_previous_tree(tmp_path):
    out = tmp_path / "data"
    (out / "actors").mkdir(parents=True)
    (out / "actors" / "retired-actor.json").write_text("{}", encoding="utf-8")
    (out / "keep.txt").write_text("old", encoding="utf-8")
    write_all(out, sample_payload())
    assert not (out / "actors" / "retired-actor.json").exists()
    assert not (out / "keep.txt").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data"]


def test_leftovers_of_a_crashed_earlier_run_do_not_matter(tmp_path):
    (tmp_path / ".data.new").mkdir()
    (tmp_path / ".data.new" / "half.json").write_text("{", encoding="utf-8")
    (tmp_path / ".data.old").mkdir()
    write_all(tmp_path / "data", sample_payload())
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data"]


# Refusals: each one leaves data/ untouched and writes no temporary directory.

def test_an_actor_without_a_name_is_refused_and_nothing_is_written(tmp_path):
    payload = sample_payload()
    del payload["actors/G0007.json"]["name"]
    err = refused(tmp_path, payload, match="actors/G0007.json")
    assert "name" in str(err)


def test_an_empty_or_padded_name_is_refused(tmp_path):
    payload = sample_payload()
    payload["actors/G0007.json"]["name"] = " APT28"
    refused(tmp_path, payload, match="name")


def test_a_refusal_into_a_missing_directory_creates_nothing(tmp_path):
    payload = sample_payload()
    del payload["actors/G0007.json"]["name"]
    with pytest.raises(WriteRefused):
        write_all(tmp_path / "data", payload)
    assert list(tmp_path.iterdir()) == []


def test_every_problem_is_reported_not_only_the_first(tmp_path):
    payload = sample_payload()
    del payload["actors/G0007.json"]["name"]
    del payload["actors/G0016.json"]["origin"]
    err = refused(tmp_path, payload)
    assert "actors/G0007.json" in str(err) and "actors/G0016.json" in str(err)
    assert len(err.problems) >= 2


def test_a_value_the_schema_forbids_deep_inside_a_file_is_refused(tmp_path):
    payload = sample_payload()
    payload["trends.json"]["notes"]["kev_monthly"] = ""
    refused(tmp_path, payload, match="trends.json")


def test_something_json_cannot_hold_is_refused_not_written_half(tmp_path):
    payload = sample_payload()
    payload["vulns.json"][0]["report_count"] = float("nan")
    refused(tmp_path, payload, match="vulns.json")


@pytest.mark.parametrize("rel", ["notes.txt", "actors/sub/x.json", "../escape.json", "/abs.json",
                                 "actors\\G0007.json", "reports/2024.json.bak", "actors/.json"])
def test_a_path_no_schema_governs_is_refused(tmp_path, rel):
    payload = sample_payload()
    payload[rel] = {}
    refused(tmp_path, payload, match="no schema|not a plain path")


@pytest.mark.parametrize("rel", ["actors/index.json", "reports/undated.json", "campaigns.json", "vulns.json", "sources.json",
                                 "resolution.json", "trends.json", "build.json", "slugs.json", "guesses.json", "NOTICE.md"])
def test_a_missing_top_level_file_is_refused(tmp_path, rel):
    payload = sample_payload()
    del payload[rel]
    refused(tmp_path, payload, match=rel.replace(".", r"\."))


def test_an_actor_page_without_a_slug_entry_is_refused(tmp_path):
    payload = sample_payload()
    payload["slugs.json"]["entries"] = [e for e in payload["slugs.json"]["entries"] if e["slug"] != "G0006"]
    refused(tmp_path, payload, match="no entry for G0006")


def test_a_live_slug_entry_without_an_actor_page_is_refused(tmp_path):
    payload = sample_payload()
    payload["slugs.json"]["entries"].append({
        "slug": "ghost-crew", "display_name": "Ghost Crew", "anchors": ["misp:ghost"],
        "first_published": "2026-09-01", "suffix": None, "retired": False, "merged_into": None})
    refused(tmp_path, payload, match="ghost-crew.*active but is not a published actor")


def test_a_retired_slug_that_is_still_a_published_actor_is_refused(tmp_path):
    payload = sample_payload()
    for entry in payload["slugs.json"]["entries"]:
        if entry["slug"] == "G0006":
            entry.update(retired=True, merged_into="G0007")
    refused(tmp_path, payload, match="G0006.*retired but is a published actor")


def test_a_slug_registry_that_breaks_its_schema_is_refused(tmp_path):
    payload = sample_payload()
    payload["slugs.json"]["entries"][0]["first_published"] = "yesterday"
    refused(tmp_path, payload, match="slugs.json")


@pytest.mark.parametrize("text", [
    "All rights reserved.",
    render_notice("2026").replace("The MITRE Corporation", "Someone"),
    render_notice("2026").replace("CC BY-NC-SA 4.0", "a licence"),
])
def test_the_notice_must_carry_the_licence_and_mitre_designation(tmp_path, text):
    payload = sample_payload()
    payload["NOTICE.md"] = text
    refused(tmp_path, payload, match="NOTICE.md")


def test_a_notice_that_is_not_text_is_refused(tmp_path):
    payload = sample_payload()
    payload["NOTICE.md"] = {"text": "x"}
    refused(tmp_path, payload, match="NOTICE.md")


def test_an_actor_file_whose_id_differs_from_its_name_is_refused(tmp_path):
    payload = sample_payload()
    payload["actors/G0006.json"]["id"] = "G0007"
    refused(tmp_path, payload, match="G0006")


def test_the_index_and_the_actor_files_must_list_the_same_actors(tmp_path):
    payload = sample_payload()
    payload["actors/index.json"] = [e for e in payload["actors/index.json"] if e["id"] != "G0006"]
    refused(tmp_path, payload, match="G0006")


def test_an_index_entry_without_a_file_is_refused(tmp_path):
    payload = sample_payload()
    del payload["actors/G0006.json"]
    refused(tmp_path, payload, match="G0006")


def test_an_index_name_that_disagrees_with_the_actor_file_is_refused(tmp_path):
    payload = sample_payload()
    for entry in payload["actors/index.json"]:
        if entry["id"] == "G0007":
            entry["name"] = "Something else"
    refused(tmp_path, payload, match="G0007")


def test_a_report_naming_an_actor_with_no_file_is_refused(tmp_path):
    payload = sample_payload()
    payload["reports/2024.json"][0]["actors"] = ["G9999"]
    refused(tmp_path, payload, match="G9999")


@pytest.mark.parametrize("rel,path", [("campaigns.json", (0, "actors")), ("vulns.json", (0, "actors"))])
def test_a_campaign_or_vuln_naming_an_actor_with_no_file_is_refused(tmp_path, rel, path):
    payload = sample_payload()
    payload[rel][path[0]][path[1]] = ["nobody-here"]
    refused(tmp_path, payload, match="nobody-here")


def test_a_trend_row_for_an_actor_with_no_file_is_refused(tmp_path):
    payload = sample_payload()
    payload["trends.json"]["new_actors"][0]["actor"] = "nobody-here"
    refused(tmp_path, payload, match="nobody-here")


def test_an_actor_listing_a_report_that_does_not_exist_is_refused(tmp_path):
    payload = sample_payload()
    payload["actors/G0007.json"]["reports"].append("a" * 40)
    refused(tmp_path, payload, match="a" * 40)


def test_a_report_in_the_wrong_year_shard_is_refused(tmp_path):
    payload = sample_payload()
    payload["reports/2025.json"].append(payload["reports/2024.json"].pop(0))
    refused(tmp_path, payload, match="2025")


def test_a_dated_report_in_the_undated_shard_is_refused(tmp_path):
    payload = sample_payload()
    payload["reports/undated.json"].append(payload["reports/2024.json"].pop(0))
    refused(tmp_path, payload, match="undated")


def test_a_report_id_may_appear_once(tmp_path):
    payload = sample_payload()
    payload["reports/2024.json"].append(copy.deepcopy(payload["reports/2024.json"][0]))
    refused(tmp_path, payload, match="more than once")


def test_report_years_must_match_the_shards_written(tmp_path):
    payload = sample_payload()
    payload["build.json"]["report_years"] = [2023, 2024]
    refused(tmp_path, payload, match="report_years")


def test_report_count_must_match_the_reports_written(tmp_path):
    payload = sample_payload()
    payload["build.json"]["report_count"] += 1
    refused(tmp_path, payload, match="report_count")


def test_recent_since_must_match_the_trends_window(tmp_path):
    payload = sample_payload()
    payload["build.json"]["recent_since"] = "1999-01-01"
    refused(tmp_path, payload, match="recent_since")


# --- The reports index must agree with the shards it summarises ---------------

def test_the_index_is_required(tmp_path):
    payload = sample_payload()
    del payload["reports/index.json"]
    refused(tmp_path, payload, match="reports/index.json: is missing")


def test_an_index_total_that_is_not_the_sum_of_the_shards_is_refused(tmp_path):
    payload = sample_payload()
    payload["reports/index.json"]["total"] += 1
    refused(tmp_path, payload, match="total is")


def test_an_index_built_at_another_time_than_build_json_is_refused(tmp_path):
    payload = sample_payload()
    payload["reports/index.json"]["built_at"] = "2020-01-01T00:00:00Z"
    refused(tmp_path, payload, match="built_at")


def test_an_indexed_report_that_is_in_no_shard_is_refused(tmp_path):
    payload = sample_payload()
    payload["reports/2024.json"].pop(0)
    refused(tmp_path, payload, match="reports/index.json")


def test_a_shard_report_that_is_not_indexed_is_refused(tmp_path):
    payload = sample_payload()
    extra = copy.deepcopy(payload["reports/2024.json"][0])
    extra["id"] = "f" * 40
    payload["reports/2024.json"].append(extra)
    info = refused(tmp_path, payload, match="not in the index")
    assert "f" * 8 in str(info)


def test_a_column_of_the_wrong_length_is_refused(tmp_path):
    payload = sample_payload()
    payload["reports/index.json"]["columns"]["title"].pop()
    refused(tmp_path, payload, match="columns.title has")


def test_an_index_that_disagrees_with_a_report_field_is_refused(tmp_path):
    payload = sample_payload()
    payload["reports/index.json"]["columns"]["title"][0] = "A different title"
    refused(tmp_path, payload, match="differs from the index rebuilt")


def test_an_index_that_leaves_out_a_kev_cve_is_refused(tmp_path):
    payload = sample_payload()
    payload["reports/index.json"]["kev"] = []
    refused(tmp_path, payload, match="reports/index.json")


def test_a_failed_swap_puts_the_previous_tree_back(tmp_path, monkeypatch):
    out = tmp_path / "data"
    out.mkdir()
    (out / "keep.txt").write_text("previous build", encoding="utf-8")
    before = snapshot(out)
    real = write_module._rename

    def flaky(src, dst):
        # The second move, the new tree into place, fails after the old one is aside.
        if str(src).endswith(".new"):
            raise OSError("disk says no")
        real(src, dst)

    monkeypatch.setattr(write_module, "_rename", flaky)
    with pytest.raises(OSError, match="disk says no"):
        write_all(out, sample_payload())
    assert snapshot(out) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data"]


def test_every_written_path_is_one_the_contract_knows(tmp_path):
    written = write_all(tmp_path / "data", sample_payload())
    assert all(schema_for(rel) or rel in NON_JSON_FILES for rel in written)
