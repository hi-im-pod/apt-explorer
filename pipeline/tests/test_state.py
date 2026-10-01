import io
import json
import tarfile

import pytest

from aptx import cli
from aptx.core import state
from aptx.core.snapshot import SnapshotStore

FEEDS = ["talos", "eset"]


def put(store, source, day, name, text):
    d = store.root / source / day
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")


def put_links(store, text="{}"):
    (store.root / "links").mkdir(exist_ok=True)
    (store.root / "links" / "status.json").write_text(text, encoding="utf-8")


def test_the_feed_sources_are_the_four_title_only_ones():
    assert sorted(cli.feed_sources()) == ["dfir", "eset", "microsoftblog", "talos"]


def test_pack_keeps_the_newest_feed_snapshot_and_the_link_results_and_nothing_else(tmp_path):
    s = SnapshotStore(tmp_path / "cache")
    put(s, "talos", "2026-09-01", "posts.json", '["old"]')
    put(s, "talos", "2026-09-28", "posts.json", '["new"]')
    put(s, "orkl", "2026-09-28", "reports.json", "raw report text")
    put_links(s)
    (s.root / "fetch-status.json").write_text("{}", encoding="utf-8")

    names = state.pack(s, tmp_path / "state.tgz", FEEDS)
    assert names == ["talos/2026-09-28/posts.json", "links/status.json"]
    with tarfile.open(tmp_path / "state.tgz") as tar:
        assert sorted(tar.getnames()) == sorted(names)


def test_a_feed_that_has_no_snapshot_yet_is_skipped(tmp_path):
    s = SnapshotStore(tmp_path / "cache")
    put(s, "talos", "2026-09-28", "posts.json", "[]")
    assert state.pack(s, tmp_path / "state.tgz", FEEDS) == ["talos/2026-09-28/posts.json"]


def test_unpack_restores_over_an_older_copy(tmp_path):
    src = SnapshotStore(tmp_path / "src")
    put(src, "eset", "2026-09-28", "posts.json", '["kept"]')
    put_links(src, json.dumps({"https://a.test/": {"ok": True}}))
    state.pack(src, tmp_path / "state.tgz", FEEDS)

    dst = SnapshotStore(tmp_path / "dst")
    put(dst, "eset", "2026-09-28", "posts.json", '["stale"]')
    state.unpack(dst, tmp_path / "state.tgz", FEEDS)
    assert dst.latest("eset", "posts.json") == b'["kept"]'
    assert json.loads((dst.root / "links" / "status.json").read_text(encoding="utf-8")) == {"https://a.test/": {"ok": True}}


def archive_with(tmp_path, *entries):
    path = tmp_path / "bad.tgz"
    with tarfile.open(path, "w:gz") as tar:
        for name, data in entries:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


@pytest.mark.parametrize("name", [
    "orkl/2026-09-28/reports.json",       # raw source text
    "talos/2026-09-28/other.json",        # wrong file name
    "malpedia/2026-09-28/posts.json",     # not a feed source
    "../escape/posts.json",               # outside the store
    "/abs/links/status.json",
    "links/status.json.bak",
])
def test_unpack_refuses_anything_outside_the_allowlist(tmp_path, name):
    bad = archive_with(tmp_path, ("links/status.json", b"{}"), (name, b"x"))
    dst = SnapshotStore(tmp_path / "dst")
    with pytest.raises(ValueError, match="not saved state"):
        state.unpack(dst, bad, FEEDS)
    assert not (tmp_path / "dst").exists() or not any((tmp_path / "dst").iterdir())


def test_unpack_refuses_a_link_that_is_not_a_plain_file(tmp_path):
    path = tmp_path / "link.tgz"
    with tarfile.open(path, "w:gz") as tar:
        info = tarfile.TarInfo("links/status.json")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tar.addfile(info)
    with pytest.raises(ValueError):
        state.unpack(SnapshotStore(tmp_path / "dst"), path, FEEDS)


def test_the_state_command_round_trips_and_needs_an_archive_to_unpack(tmp_path):
    s = SnapshotStore(tmp_path / "cache")
    put(s, "talos", "2026-09-28", "posts.json", "[]")
    assert cli.main(["state", "pack", str(tmp_path / "s.tgz")], store=s) == 0
    other = SnapshotStore(tmp_path / "other")
    assert cli.main(["state", "unpack", str(tmp_path / "s.tgz")], store=other) == 0
    assert other.latest("talos", "posts.json") == b"[]"
    assert cli.main(["state", "unpack", str(tmp_path / "missing.tgz")], store=other) == 1
