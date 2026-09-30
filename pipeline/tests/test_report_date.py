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
