import gzip

import httpx
import pytest
import respx

from aptx.core import http
from aptx.core.snapshot import ShrunkSnapshotError, SnapshotStore
from aptx.sources import epss
from aptx.sources.base import Connector
from aptx.sources.epss import EpssConnector

COMMENT = "#model_version:v2025.03.14,score_date:2026-09-28T12:55:00Z\n"
HEADER = "cve,epss,percentile\n"
GOOD = [
    "CVE-2021-44228,0.94358,0.99991",
    "cve-2023-23397,0.91207,0.99634",
    "CVE-2022-30190,0.00043,0.0987",
]


def payload(rows=GOOD, comment=COMMENT, header=HEADER):
    return gzip.compress((comment + header + "\n".join(rows) + "\n").encode("utf-8"))


@pytest.fixture(autouse=True)
def small_file(monkeypatch):
    monkeypatch.setattr(epss, "MIN_ROWS", 3)


@pytest.fixture
def store(tmp_path):
    s = SnapshotStore(tmp_path)
    s.save("epss", epss.SNAPSHOT, payload())
    return s


def vulns(store):
    return {v.cve: v for v in EpssConnector().normalize(store).vulns}


def test_each_row_becomes_a_score_for_its_cve(store):
    v = vulns(store)["CVE-2021-44228"]
    assert (v.epss, v.epss_percentile) == (0.94358, 0.99991)
    assert (v.kev_date_added, v.ransomware, v.vendor, v.product) == (None, None, None, None)


def test_a_cve_is_upper_cased(store):
    assert "CVE-2023-23397" in vulns(store)


def test_a_repeated_cve_keeps_its_first_score(tmp_path):
    s = SnapshotStore(tmp_path)
    s.save("epss", epss.SNAPSHOT, payload(GOOD + ["CVE-2021-44228,0.1,0.2"]))
    assert vulns(s)["CVE-2021-44228"].epss == 0.94358


@pytest.mark.parametrize("bad", ["CVE-21-1,0.5,0.5", "CVE-2021-44228,1.5,0.5", "CVE-2021-44229,0.5,-0.1",
                                 "CVE-2021-44230,high,0.5", "CVE-2021-44231", " "])
def test_a_malformed_row_is_dropped_and_counted(tmp_path, caplog, bad):
    s = SnapshotStore(tmp_path)
    s.save("epss", epss.SNAPSHOT, payload(GOOD + [bad]))
    with caplog.at_level("WARNING"):
        got = vulns(s)
    assert set(got) == {"CVE-2021-44228", "CVE-2023-23397", "CVE-2022-30190"}
    assert ("dropped 1 malformed" in caplog.text) 



def test_retrieved_at_is_the_snapshot_date_not_today(tmp_path):
    d = tmp_path / "epss" / "2026-01-02"
    d.mkdir(parents=True)
    (d / epss.SNAPSHOT).write_bytes(payload())
    b = EpssConnector().normalize(SnapshotStore(tmp_path))
    assert {v.retrieved_at for v in b.vulns} == {"2026-01-02"}


def test_no_snapshot_gives_an_empty_bundle(tmp_path):
    b = EpssConnector().normalize(SnapshotStore(tmp_path))
    assert (b.source, b.vulns) == ("epss", [])


def test_is_a_connector():
    assert isinstance(EpssConnector(), Connector)
    assert EpssConnector.name == "epss"


@pytest.fixture
def fast_http(monkeypatch):
    monkeypatch.setattr(http, "MIN_INTERVAL", 0)
    monkeypatch.setattr(http, "BACKOFF_BASE", 0)


@respx.mock
def test_fetch_saves_the_file(tmp_path, fast_http):
    body = payload()
    respx.get(epss.EPSS_URL).mock(return_value=httpx.Response(200, content=body))
    s = SnapshotStore(tmp_path)
    EpssConnector().fetch(s)
    assert s.latest("epss", epss.SNAPSHOT) == body


@respx.mock
@pytest.mark.parametrize("body", [
    payload(comment=""),
    payload(header="cve,score,percentile\n"),
    payload(rows=GOOD[:2]),
    payload(rows=["junk,1,1"] * 5),
])
def test_fetch_refuses_a_file_that_is_not_an_epss_export(tmp_path, fast_http, body):
    respx.get(epss.EPSS_URL).mock(return_value=httpx.Response(200, content=body))
    s = SnapshotStore(tmp_path)
    with pytest.raises(ValueError):
        EpssConnector().fetch(s)
    assert s.latest_date("epss") is None


@respx.mock
def test_a_shrunken_file_keeps_the_old_snapshot(tmp_path, fast_http):
    old = tmp_path / "epss" / "2026-01-02"
    old.mkdir(parents=True)
    (old / epss.SNAPSHOT).write_bytes(payload() + b"\0" * 100_000)
    respx.get(epss.EPSS_URL).mock(return_value=httpx.Response(200, content=payload()))
    s = SnapshotStore(tmp_path)
    with pytest.raises(ShrunkSnapshotError):
        EpssConnector().fetch(s)
    assert s.latest_date("epss") == "2026-01-02"
