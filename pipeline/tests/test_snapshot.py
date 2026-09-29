import pytest
from aptx.core.snapshot import SnapshotStore, ShrunkSnapshotError

def test_save_then_latest_round_trips(tmp_path):
    s = SnapshotStore(tmp_path)
    s.save("kev", "catalog.json", b'{"a":1}')
    assert s.latest("kev", "catalog.json") == b'{"a":1}'

def test_shrunken_payload_is_refused_and_old_one_kept(tmp_path):
    s = SnapshotStore(tmp_path)
    s.save("kev", "catalog.json", b"x" * 1000)
    with pytest.raises(ShrunkSnapshotError):
        s.save("kev", "catalog.json", b"x" * 100)
    assert s.latest("kev", "catalog.json") == b"x" * 1000

def test_latest_is_none_when_absent(tmp_path):
    assert SnapshotStore(tmp_path).latest("nope", "x.json") is None
