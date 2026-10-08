import hashlib
import json
import shutil
from pathlib import Path

import pytest

from aptx.build.write import WriteRefused
from aptx.freeze import freeze, main

SAMPLE = Path(__file__).parent / "fixtures" / "sample_data"
SHA = "f387067add2f6b34b9f7cd0aba1c7fdc12b7dc6b"


@pytest.fixture
def data(tmp_path):
    out = tmp_path / "data"
    shutil.copytree(SAMPLE, out)
    return out


def test_every_file_is_fingerprinted_in_the_form_sha256sum_reads(data):
    manifest, sums = freeze(data, "v1.0.0", SHA, "123")
    files = sorted(p.relative_to(data).as_posix() for p in data.rglob("*") if p.is_file())
    assert [f["path"] for f in manifest["files"]] == files
    first = manifest["files"][0]
    assert first["sha256"] == hashlib.sha256((data / first["path"]).read_bytes()).hexdigest()
    assert sums.splitlines()[0] == f"{first['sha256']}  data/{first['path']}"


def test_the_manifest_names_the_build_and_counts_what_is_in_it(data):
    manifest, _ = freeze(data, "v1.0.0", SHA, "123")
    built = json.loads((data / "build.json").read_text(encoding="utf-8"))["built_at"]
    assert (manifest["version"], manifest["source_commit"], manifest["workflow_run"]) == ("v1.0.0", SHA, "123")
    assert manifest["data_built_at"] == built
    assert manifest["composition"]["reports"] == json.loads(
        (data / "reports" / "index.json").read_text(encoding="utf-8"))["total"]


def test_freezing_the_same_tree_twice_gives_the_same_files(data):
    assert freeze(data, "v1.0.0", SHA) == freeze(data, "v1.0.0", SHA)


def test_a_tree_the_pipeline_would_refuse_cannot_be_frozen(data):
    (data / "build.json").write_text("{}", encoding="utf-8")
    with pytest.raises(WriteRefused):
        freeze(data, "v1.0.0", SHA)


@pytest.mark.parametrize("version, commit", [("1.0", SHA), ("v1.0.0", "f387067"), ("latest", SHA)])
def test_a_loose_version_or_a_short_commit_is_refused(data, version, commit):
    with pytest.raises(ValueError):
        freeze(data, version, commit)


def test_the_command_writes_both_files_and_fails_cleanly(data, tmp_path, capsys):
    out = tmp_path / "release"
    assert main(["--data", str(data), "--version", "v1.0.0", "--commit", SHA, "--out", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["MANIFEST.json", "SHA256SUMS"]
    assert main(["--data", str(data), "--version", "nope", "--commit", SHA, "--out", str(out)]) == 1
    assert "not frozen" in capsys.readouterr().err
