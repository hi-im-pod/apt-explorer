from aptx.core.dates import resolve_report_date
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
