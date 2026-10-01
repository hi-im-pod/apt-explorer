"""The release script that keeps the saved state, run against a stand-in for the gh CLI.

The stand-in keeps one fake draft release in a folder, so nothing here touches
GitHub. It answers only the calls the script makes and fails on any other.
"""
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "pipeline-state.sh"
BASH = shutil.which("bash")


def bash_path(path):
    # Git Bash's tar reads "C:/x" as a file on a host called C.
    text = Path(path).as_posix()
    return f"/{text[0].lower()}{text[2:]}" if text[1:2] == ":" else text

pytestmark = pytest.mark.skipif(BASH is None, reason="needs bash")

STUB_GH = r"""#!/usr/bin/env bash
set -euo pipefail
d="$STUB_DIR"
mkdir -p "$d/assets"
args=("$@")
method=GET; input=""; url=""
i=0
while [ $i -lt ${#args[@]} ]; do
  a="${args[$i]}"
  case "$a" in
    api) ;;
    -X) i=$((i+1)); method="${args[$i]}" ;;
    -H|-f|-F|--jq) i=$((i+1)) ;;
    --input) i=$((i+1)); input="${args[$i]}" ;;
    --paginate) ;;
    *) url="$a" ;;
  esac
  i=$((i+1))
done
echo "$method $url" >> "$d/calls.log"
case "$method $url" in
  "GET repos/o/r/releases")
    if [ -f "$d/release" ]; then cat "$d/release"; fi ;;
  "POST repos/o/r/releases")
    echo 42 > "$d/release"; echo 42 ;;
  "GET repos/o/r/releases/42")
    for f in $(ls "$d/assets" | sort -r); do
      echo "${f%%_*} $(wc -c < "$d/assets/$f" | tr -d ' ') ${f#*_}"
    done ;;
  "GET repos/o/r/releases/assets/"*)
    cat "$d/assets/${url##*/}_"* ;;
  "POST https://uploads.github.com/repos/o/r/releases/42/assets?name="*)
    n=$(( $(cat "$d/seq" 2>/dev/null || echo 0) + 1 )); echo $n > "$d/seq"
    cp "$input" "$d/assets/$(printf '%04d' $n)_${url##*name=}"; echo "$n" ;;
  "DELETE repos/o/r/releases/assets/"*)
    rm -f "$d/assets/${url##*/}_"* ;;
  *) echo "stub gh: unhandled $method $url" >&2; exit 9 ;;
esac
"""


class Release:
    def __init__(self, tmp_path):
        self.dir = tmp_path / "release"
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        (self.bin / "gh").write_text(STUB_GH, encoding="utf-8", newline="\n")
        self.out = tmp_path / "output.txt"
        self.out.write_text("", encoding="utf-8")
        self.tmp = tmp_path

    def run(self, *args, run_id="1"):
        args = [bash_path(a) if isinstance(a, Path) else a for a in args]
        env = dict(os.environ)
        env.update(
            PATH=f"{self.bin}{os.pathsep}{env['PATH']}",
            STUB_DIR=bash_path(self.dir),
            GITHUB_REPOSITORY="o/r",
            GITHUB_OUTPUT=bash_path(self.out),
            GITHUB_RUN_ID=run_id,
        )
        return subprocess.run([BASH, bash_path(SCRIPT), *args], env=env, capture_output=True, text=True)

    def archive(self, kb, name="state.tgz"):
        blob = self.tmp / "blob"
        blob.write_bytes(os.urandom(kb * 1024))
        path = self.tmp / name
        with tarfile.open(path, "w:gz") as tar:
            tar.add(blob, arcname="blob")
        return path

    def assets(self):
        folder = self.dir / "assets"
        return sorted(p.name.split("_", 1)[1] for p in folder.iterdir()) if folder.exists() else []

    def found(self):
        return self.out.read_text(encoding="utf-8").strip().splitlines()[-1]


@pytest.fixture
def release(tmp_path):
    return Release(tmp_path)


def test_a_fetch_with_nothing_stored_succeeds_and_says_so(release):
    done = release.run("fetch", (release.tmp / "in" / "state.tgz"))
    assert done.returncode == 0, done.stderr
    assert release.found() == "found=false"


def test_what_is_stored_comes_back_unchanged(release):
    first = release.archive(40)
    assert release.run("store", first).returncode == 0
    dest = release.tmp / "in" / "state.tgz"
    done = release.run("fetch", dest)
    assert done.returncode == 0, done.stderr
    assert release.found() == "found=true"
    assert dest.read_bytes() == first.read_bytes()


def test_the_release_is_made_once_and_only_the_newest_three_assets_stay(release):
    for run_id in "12345":
        assert release.run("store", release.archive(40), run_id=run_id).returncode == 0
    assert release.assets() == ["state-3-1.tgz", "state-4-1.tgz", "state-5-1.tgz"]
    calls = (release.dir / "calls.log").read_text(encoding="utf-8").splitlines()
    assert calls.count("POST repos/o/r/releases") == 1


def test_a_state_far_smaller_than_the_last_is_refused_and_not_uploaded(release):
    assert release.run("store", release.archive(40), run_id="1").returncode == 0
    done = release.run("store", release.archive(4, "small.tgz"), run_id="2")
    assert done.returncode == 1
    assert release.assets() == ["state-1-1.tgz"]


@pytest.mark.parametrize("content", [b"not a tarball", b""])
def test_a_file_that_is_not_a_usable_archive_is_refused(release, content):
    bad = release.tmp / "bad.tgz"
    bad.write_bytes(content)
    assert release.run("store", bad).returncode != 0
    assert release.assets() == []


def test_an_unknown_subcommand_is_a_usage_error(release):
    assert release.run("bogus").returncode == 2
