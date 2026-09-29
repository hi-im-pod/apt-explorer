import json
import re
from pathlib import Path

import httpx
import pytest
import respx

from aptx.core import http
from aptx.core.snapshot import SnapshotStore
from aptx.sources.base import Connector
from aptx.sources.kev import KEV_URL, SNAPSHOT, KevConnector

FIX = Path(__file__).parent / "fixtures" / "kev_min.json"
CVE = re.compile(r"^CVE-[0-9]{4}-[0-9]{4,7}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@pytest.fixture
def store(tmp_path):
    s = SnapshotStore(tmp_path)
    s.save("kev", SNAPSHOT, FIX.read_bytes())
    return s


@pytest.fixture
def no_wait(monkeypatch):
    # test_http changes these module globals and never restores them, so every
    # test that goes through the client sets them itself.
    monkeypatch.setattr(http, "MIN_INTERVAL", 0)
    monkeypatch.setattr(http, "BACKOFF_BASE", 0)


def by_cve(bundle):
    return {v.cve: v for v in bundle.vulns}


def test_is_a_connector_named_kev():
    assert KevConnector.name == "kev"
    assert isinstance(KevConnector(), Connector)


def test_ransomware_flag_maps_known_unknown_and_missing(store):
    v = by_cve(KevConnector().normalize(store))
    assert v["CVE-2024-57728"].ransomware is True        # "Known"
    assert v["CVE-2023-23397"].ransomware is False       # "Unknown"
    assert v["CVE-2021-44228"].ransomware is None        # field absent


def test_date_added_is_parsed(store):
    v = by_cve(KevConnector().normalize(store))
    assert v["CVE-2023-23397"].kev_date_added == "2023-03-14"
    assert v["CVE-2024-57728"].kev_date_added == "2026-04-24"


def test_vendor_and_product_are_trimmed_and_blank_becomes_none(store):
    # The live catalogue has values such as "SimpleHelp " and
    # " Endpoint Manager (EPM)". Published labels must be trimmed.
    v = by_cve(KevConnector().normalize(store))
    assert v["CVE-2024-57728"].vendor == "SimpleHelp"
    assert v["CVE-2026-1603"].product == "Endpoint Manager (EPM)"
    assert v["CVE-2021-44228"].vendor == "Apache"
    assert v["CVE-2021-44228"].product is None


def test_cve_ids_are_upper_cased_and_malformed_ones_dropped(store, caplog):
    with caplog.at_level("WARNING"):
        b = KevConnector().normalize(store)
    assert set(by_cve(b)) == {"CVE-2024-57728", "CVE-2023-23397", "CVE-2026-1603", "CVE-2021-44228"}
    assert all(CVE.fullmatch(v.cve) for v in b.vulns)
    assert "CVE-2023-2" in caplog.text


def test_records_meet_the_contract_and_carry_the_snapshot_date(store):
    b = KevConnector().normalize(store)
    assert b.source == "kev"
    for v in b.vulns:
        assert v.kev_date_added is None or DATE.fullmatch(v.kev_date_added)
        for label in (v.vendor, v.product):
            assert label is None or (label == label.strip() and label and "\n" not in label)
        # The normalized data is only as fresh as the snapshot it came from,
        # which may be older than today when this week's fetch failed.
        assert v.retrieved_at == store.latest_date("kev")


def test_a_repeated_cve_is_kept_once(tmp_path):
    rec = {"cveID": "CVE-2023-23397", "vendorProject": "Microsoft", "product": "Office",
           "dateAdded": "2023-03-14", "knownRansomwareCampaignUse": "Unknown"}
    s = SnapshotStore(tmp_path)
    s.save("kev", SNAPSHOT, json.dumps({"vulnerabilities": [rec, rec]}).encode())
    assert [v.cve for v in KevConnector().normalize(s).vulns] == ["CVE-2023-23397"]


def test_no_snapshot_gives_an_empty_bundle(tmp_path):
    b = KevConnector().normalize(SnapshotStore(tmp_path))
    assert b.source == "kev" and b.vulns == []


@respx.mock
def test_fetch_saves_the_catalogue(tmp_path, no_wait):
    respx.get(KEV_URL).mock(return_value=httpx.Response(200, content=FIX.read_bytes()))
    s = SnapshotStore(tmp_path)
    KevConnector().fetch(s)
    assert s.latest("kev", SNAPSHOT) == FIX.read_bytes()


@respx.mock
@pytest.mark.parametrize("body", [b'{"vulnerabilities": []}', b"<html>maintenance</html>", b'{"count": 0}'])
def test_fetch_refuses_a_catalogue_without_vulnerabilities(tmp_path, no_wait, body):
    # A 200 with an empty list or an error page would otherwise become the
    # newest snapshot and make the source look fresh. Raising lets the CLI
    # mark KEV stale and keep the last good catalogue.
    respx.get(KEV_URL).mock(return_value=httpx.Response(200, content=body))
    s = SnapshotStore(tmp_path)
    with pytest.raises(ValueError):
        KevConnector().fetch(s)
    assert s.latest("kev", SNAPSHOT) is None
