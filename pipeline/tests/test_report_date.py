from aptx.core.dates import resolve_report_date, split_title_date
from aptx.core.urls import norm_url

LIB = {"blog.talosintelligence.com/x": "2026-09-20"}

def test_malpedia_library_date_wins():
    assert resolve_report_date(["https://blog.talosintelligence.com/x/"], LIB, "0001-01-01T00:00:00Z", "2026-09-29T02:02:37Z") == ("2026-09-20", "malpedia-library")

def test_file_metadata_when_real():
    assert resolve_report_date([], {}, "2021-03-02T00:00:00Z", "2023-01-01T00:00:00Z") == ("2021-03-02", "file-metadata")

def test_ingest_date_is_last_resort_and_labelled():
    assert resolve_report_date([], {}, "0001-01-01T00:00:00Z", "2023-01-01T00:00:00Z") == ("2023-01-01", "orkl-ingest")

def test_nothing_usable():
    assert resolve_report_date([], {}, None, None) == (None, "unknown")


# Beyond the plan's four cases: the library lookup and the report lookup must
# share one normalizer, or a report and its Malpedia entry never meet.

def test_norm_url_strips_scheme_www_and_trailing_slash_and_lowercases():
    assert norm_url("https://www.Example.com/a/") == norm_url("http://example.com/a") == "example.com/a"

def test_first_matching_url_wins_and_empty_urls_are_skipped():
    lib = {"example.com/b": "2022-02-02", "example.com/c": "2023-03-03"}
    urls = ["", "https://example.com/a", "https://www.example.com/b/", "https://example.com/c"]
    assert resolve_report_date(urls, lib, None, None) == ("2022-02-02", "malpedia-library")

def test_an_unusable_library_date_falls_through_instead_of_landing_in_year_1():
    lib = {"example.com/a": "0001-01-01"}
    assert resolve_report_date(["https://example.com/a"], lib, "2021-03-02", None) == ("2021-03-02", "file-metadata")


# A VX-Underground title often starts with the date the collection filed the paper under. File
# metadata for those papers is frequently years off, so the title's own date is better evidence.

def test_a_date_prefix_is_split_from_the_title():
    assert split_title_date("2014-11-14 - OnionDuke- APT Attacks Via the Tor Network") == (
        "OnionDuke- APT Attacks Via the Tor Network", "2014-11-14")


def test_a_title_without_a_date_prefix_is_left_alone():
    assert split_title_date("APT28 in 2014-11-14 - a retrospective") == ("APT28 in 2014-11-14 - a retrospective", None)
    assert split_title_date("2014 - Year in review") == ("2014 - Year in review", None)


def test_an_impossible_or_ancient_prefix_is_still_dropped_from_the_title_but_gives_no_date():
    # The prefix is filing noise either way, so the title loses it, but only a real date counts.
    assert split_title_date("2014-13-45 - Something") == ("Something", None)
    assert split_title_date("1970-01-01 - Something") == ("Something", None)


def test_a_title_that_is_only_a_date_keeps_its_text():
    assert split_title_date("2014-11-14 -") == ("2014-11-14 -", None)


def test_the_title_date_beats_file_metadata_but_not_the_library():
    assert resolve_report_date([], {}, "2022-05-28T21:52:51Z", "2023-01-12T15:06:43Z", "2016-07-13") == (
        "2016-07-13", "title-date")
    lib = {"example.com/a": "2016-07-20"}
    assert resolve_report_date(["https://example.com/a"], lib, None, None, "2016-07-13") == (
        "2016-07-20", "malpedia-library")


def test_a_title_date_after_ingest_is_not_trusted():
    # A paper cannot be published after ORKL added it, so such a prefix is a typo or a filing mistake.
    assert resolve_report_date([], {}, "2022-05-28", "2023-01-12T15:06:43Z", "2024-02-01") == (
        "2022-05-28", "file-metadata")


def test_a_doubled_prefix_is_removed_in_full():
    # Four 2017 and 2021 papers are filed as "DATE - DATE - Title".
    assert split_title_date("2017-06-12 - 2017-06-12 - LOKI BOT MALSPAM") == ("LOKI BOT MALSPAM", "2017-06-12")


# A blog post's address often carries its date. Upload folders do not, because a file can be
# uploaded long after the report it belongs to.

def test_a_blog_style_address_gives_its_date():
    from aptx.core.dates import url_date
    assert url_date("https://blog.example.com/2021/05/31/apt-thing/") == "2021-05-31"
    assert url_date("https://example.com/research/2019/11/slug") == "2019-11-01"
    assert url_date("https://example.com/2019/11") == "2019-11-01"


def test_an_address_without_a_real_date_gives_none():
    from aptx.core.dates import url_date
    for url in (None, "", "https://example.com/a/b", "https://example.com/2019/13/slug",
                "https://example.com/1985/01/slug", "https://example.com/v2019/05/x",
                "https://example.com/report-2019-05.pdf"):
        assert url_date(url) is None, url


def test_an_upload_folder_date_is_not_a_publication_date():
    from aptx.core.dates import url_date
    assert url_date("https://example.com/wp-content/uploads/2022/03/report.pdf") is None
    assert url_date("https://example.com/media/2022/03/report.pdf") is None


def test_a_wayback_address_gives_its_capture_day_and_the_wrapped_address_its_own_date():
    from aptx.core.dates import url_date, wayback_date
    url = "https://web.archive.org/web/20160304120000/http://example.com/2015/07/02/slug/"
    assert wayback_date(url) == "2016-03-04"
    assert url_date(url) == "2015-07-02"
    assert wayback_date("https://example.com/2015/07/02/slug/") is None
    assert url_date("https://web.archive.org/web/20160304120000id_/http://example.com/a") is None


def test_the_address_date_beats_file_metadata_but_not_the_title_date():
    url = "https://example.com/2021/05/31/slug"
    assert resolve_report_date([url], {}, "2022-01-01", "2023-01-01") == ("2021-05-31", "url-date")
    assert resolve_report_date([url], {}, None, "2023-01-01", "2021-05-20") == ("2021-05-20", "title-date")


def test_an_address_date_after_ingest_is_not_trusted():
    url = "https://example.com/2024/05/31/slug"
    assert resolve_report_date([url], {}, None, "2023-01-01") == ("2023-01-01", "orkl-ingest")


def test_a_library_date_a_year_or_more_before_the_address_date_is_a_wrong_year():
    url = "https://example.com/2021/05/31/slug"
    assert resolve_report_date([url], {"example.com/2021/05/31/slug": "2020-05-31"}, None, None) == (
        "2021-05-31", "url-date")
    # Inside a year the library is trusted: a copy can appear a little before the post's own date.
    assert resolve_report_date([url], {"example.com/2021/05/31/slug": "2020-06-01"}, None, None) == (
        "2020-06-01", "malpedia-library")


def test_a_wayback_capture_is_used_only_before_the_ingest_fallback():
    url = "https://web.archive.org/web/20160304/http://example.com/a"
    assert resolve_report_date([url], {}, "2015-01-01", "2023-01-01") == ("2015-01-01", "file-metadata")
    assert resolve_report_date([url], {}, None, "2023-01-01") == ("2016-03-04", "wayback-capture")
    assert resolve_report_date([url], {}, None, "2015-01-01") == ("2015-01-01", "orkl-ingest")
