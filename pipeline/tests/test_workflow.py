"""Properties of the workflow files that a careless edit could quietly break.

The files are read as text, so each job is cut out by its two-space-indented key.
"""
import re
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"
GATE = "github.event_name != 'schedule' || vars.PUBLISH_ENABLED == 'true'"


def jobs(name: str) -> dict[str, str]:
    text = (WORKFLOWS / name).read_text(encoding="utf-8")
    body = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"(?m)^  ([a-z][a-z-]*):\s*$", body)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def test_the_weekly_build_has_the_jobs_the_state_design_needs():
    assert list(jobs("build.yml")) == ["state-in", "data", "state-out", "site", "deploy"]


def test_the_publish_gate_still_guards_every_job_that_starts_a_scheduled_run():
    j = jobs("build.yml")
    for name in ("state-in", "data"):
        assert f"if: {GATE}" in j[name], name
    assert "if: vars.PUBLISH_ENABLED == 'true'" in j["deploy"]
    assert f"if: {GATE}" in jobs("keepalive.yml")["touch"]


def test_only_the_two_state_jobs_can_write_to_the_repository():
    j = jobs("build.yml")
    writers = {name for name, text in j.items() if "contents: write" in text}
    assert writers == {"state-in", "state-out"}
    assert "contents: read" in j["data"]


def test_the_job_that_runs_the_pipeline_never_touches_the_release():
    data = jobs("build.yml")["data"]
    assert "pipeline-state.sh" not in data
    assert "GH_TOKEN" not in data


def test_the_state_jobs_run_nothing_but_the_release_script():
    j = jobs("build.yml")
    for name in ("state-in", "state-out"):
        runs = re.findall(r"(?m)^\s+run: (.+)$", j[name])
        assert len(runs) == 1 and runs[0].startswith("bash .github/scripts/pipeline-state.sh "), (name, runs)


def test_the_data_job_is_ordered_after_the_saved_state_arrives_and_before_it_is_stored():
    j = jobs("build.yml")
    assert "needs: [state-in]" in j["data"]
    assert "needs: [data]" in j["state-out"]
    data = j["data"]
    assert data.index("state unpack") < data.index("aptx run --out ../data\n")
    assert data.index("aptx run --out ../data --skip-fetch") < data.index("state pack")


def test_the_keepalive_workflow_can_only_read_the_cache():
    text = (WORKFLOWS / "keepalive.yml").read_text(encoding="utf-8")
    assert "permissions: {}" in text
    assert "actions/cache/restore@" in text
    assert "actions/cache/save" not in text
    assert "restore-keys: snapshots-" in text


def test_every_action_is_pinned_to_a_full_commit():
    for path in WORKFLOWS.glob("*.yml"):
        for use in re.findall(r"(?m)^\s*- uses: (\S+)|^\s+uses: (\S+)", path.read_text(encoding="utf-8")):
            ref = next(u for u in use if u)
            assert re.search(r"@[0-9a-f]{40}$", ref), (path.name, ref)
