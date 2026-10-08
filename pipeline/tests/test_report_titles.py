import pytest

from aptx.core.report_titles import clean_title, is_error_page, title_domain


@pytest.mark.parametrize("raw, shown", [
    ("Microsoft Word - TR62.doc", "TR62"),
    ("Microsoft PowerPoint - VB2011-Presentation-Edwards-Nazario.pptx", "VB2011-Presentation-Edwards-Nazario"),
    ("Microsoft Word - Getting In Bed With Robin Sage v1.0", "Getting In Bed With Robin Sage v1.0"),
    ("Macintosh HD:Users:Shared:dd:4work:Bitdefender-PR-Whitepaper-Chafer-creat4491-en_EN:"
     "Bitdefender-PR-Whitepaper-Chafer-creat4491-en_EN.indd", "Bitdefender-PR-Whitepaper-Chafer-creat4491-en EN"),
    ("RawPOS%20Technical%20Brief.pdf", "RawPOS Technical Brief"),
    ("Bitdefender_In-depth_analysis_of_APT28%E2%80%93The_Political_Cyber-Espionage.pdf",
     "Bitdefender In-depth analysis of APT28–The Political Cyber-Espionage"),
    ("m-trends-2024.pdf", "m-trends-2024"),
    ("w32_stuxnet_dossier.pdf", "w32 stuxnet dossier"),
    ("Anunak_APT_against_financial_institutions", "Anunak APT against financial institutions"),
    ("securelist.com-The Icefog APT Hits US Targets With Java Backdoor",
     "The Icefog APT Hits US Targets With Java Backdoor"),
    ("  A   normal\ttitle ", "A normal title"),
])
def test_file_name_titles_are_tidied(raw, shown):
    assert clean_title(raw) == shown


@pytest.mark.parametrize("raw", [
    "BKDR_SARHUST.A", "WORM_EMUDBOT.JP", "skywiper_v1.05", "unit42.paloaltonetworks.com",
    "404 Keylogger Campaigns", "404 — File still found", "PowerPoint attachments, Agent Tesla and code reuse in malware",
    "“Page Not Found”- REvil Darknet Services Offline After Attack Last Weekend",
])
def test_titles_that_read_as_names_are_left_alone(raw):
    assert clean_title(raw) == raw


@pytest.mark.parametrize("raw", [
    "PowerPoint Presentation", "powerpoint presentation", "Word Template", "PowerPoint 簡報", "Untitled", "Title",
    "404", "Not Found", "404: This page could not be found.", "This Page Could Not Be Found",
    "File not found · github/codeql", "", "   ", None,
])
def test_placeholders_and_error_pages_name_no_report(raw):
    assert clean_title(raw) is None


def test_error_pages_are_recognised_exactly():
    assert is_error_page("404: This page could not be found.")
    assert not is_error_page("404 Keylogger Campaigns")
    assert not is_error_page(None)


def test_the_domain_prefix_is_read_for_the_publisher():
    assert title_domain("securelist.com-The Icefog APT") == "securelist.com"
    assert title_domain("blog.truesec.com-Collaboration between FIN7 and RYUK") == "blog.truesec.com"
    assert title_domain("The Icefog APT") is None


@pytest.mark.parametrize("url, title", [
    ("https://blogs.blackberry.com/en/2019/07/threat-spotlight-sodinokibi", "Threat spotlight sodinokibi"),
    ("https://posts.specterops.io/introducing-venator-a-macos-tool-34055a017e56", "Introducing venator a macos tool"),
    ("https://www.cylance.com/en_us/blog/threat-spotlight-locky-ransomware.html", "Threat spotlight locky ransomware"),
    ("https://usa.kaspersky.com/blog/sas-2023-research/29254/", "Sas 2023 research"),
    ("https://cert.gov.ua/article/2807", None),
    ("https://apt.etda.or.th/cgi-bin/showcard.cgi?u=1", None),
    ("https://www.hybrid-analysis.com/sample/dfc56a704b5e031f3b0d2d0ea1d06f9157758ad950483b44ac4b77d33293cb38", None),
    (None, None),
])
def test_a_title_is_read_from_the_address_only_when_it_has_words(url, title):
    from aptx.core.report_titles import title_from_url
    assert title_from_url(url) == title
