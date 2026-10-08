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


def test_only_a_known_vendor_counts_as_a_publisher_from_orkls_authors():
    from aptx.core.publishers import known_publisher
    assert known_publisher("Crowdstrike") == "CrowdStrike"
    assert known_publisher("Insikt Group® by Recorded Future®") == "Recorded Future"
    for name in ("Appendix", "Blog", "Doug Pearson", "CISA, NSA, FBI", None):
        assert known_publisher(name) is None


@pytest.mark.parametrize("title, name", [
    ("securelist.com-The Icefog APT Hits US Targets With Java Backdoor", "Kaspersky"),
    ("The Naikon APT - Securelist", "Kaspersky"),
    ("2020.10.05_-_MosaicRegressor_Lurking_in_the_Shadows_of_UEFI_Securelist_2020", "Kaspersky"),
    ("Cisco's Talos Intelligence Group Blog: Korea In The Crosshairs", "Cisco Talos"),
    ("ChessMaster Adds Updated Tools to Its Arsenal - TrendLabs Security Intelligence Blog", "Trend Micro"),
    ("ESET-LoJax", "ESET"),
    ("Strategic web compromises in the Middle East with a pinch of Candiru _ WeLiveSecurity", "ESET"),
    ("Shifting Tactics: Tracking changes in years-long espionage campaign against Tibetans - The Citizen Lab",
     "Citizen Lab"),
    ("CryptoCore-Lazarus-Clearsky", "ClearSky"),
    ("unit42.paloaltonetworks.com-xHunt Campaign New BumbleBee Webshell", "Palo Alto Networks"),
    ("proofpoint.com-TA413 Leverages New FriarFox Browser Extension", "Proofpoint"),
    ("OnionDuke APT Attacks Via the Tor Network", None),
    ("Esetting the scene", None),
])
def test_a_title_that_names_its_vendors_site_gives_the_publisher(title, name):
    from aptx.core.publishers import publisher_in_title
    assert publisher_in_title(title) == name
