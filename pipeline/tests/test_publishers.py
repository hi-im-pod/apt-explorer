import pytest

from aptx.core.publishers import canonical_publisher, publisher_for_url


@pytest.mark.parametrize("raw, name", [
    ("Crowdstrike", "CrowdStrike"), ("crowdstrike", "CrowdStrike"), ("CrowdStrike", "CrowdStrike"),
    ("Palo Alto", "Palo Alto Networks"), ("PaloAlto", "Palo Alto Networks"), ("palo alto networks", "Palo Alto Networks"),
    ("Checkpoint", "Check Point"), ("G Data", "G DATA"), ("CERT_UA", "CERT-UA"), ("TheDFIRreport", "The DFIR Report"),
    ("Kaspersky Lab", "Kaspersky"), ("Microsoft Security", "Microsoft"), ("ESET Research", "ESET"),
    ("  Some   Lab ", "Some Lab"),
])
def test_one_publisher_has_one_name(raw, name):
    assert canonical_publisher(raw) == name


def test_no_name_is_none():
    assert canonical_publisher(None) is None
    assert canonical_publisher("   ") is None


@pytest.mark.parametrize("url, name", [
    ("https://securelist.com/the-naikon-apt/", "Kaspersky"),
    ("https://unit42.paloaltonetworks.com/x/", "Palo Alto Networks"),
    ("https://blog.talosintelligence.com/x", "Cisco Talos"),
    ("https://www.welivesecurity.com/2021/x", "ESET"),
    ("https://WWW.BleepingComputer.com/news/x", "BleepingComputer"),
])
def test_a_publishers_own_site_names_it(url, name):
    assert publisher_for_url(url) == name


@pytest.mark.parametrize("url", [
    None, "", "https://papers.vx-underground.org/x.pdf", "https://github.com/x/y", "https://medium.com/@a/b",
    "https://web.archive.org/web/2016/https://securelist.com/x", "https://notsecurelist.com/x",
])
def test_a_host_that_runs_no_publisher_names_nobody(url):
    assert publisher_for_url(url) is None
