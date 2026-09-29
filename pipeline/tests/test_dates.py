from aptx.core.dates import parse_date

def test_iso_datetime_becomes_date():
    assert parse_date("2026-09-29T02:02:37.917908Z") == "2026-09-29"

def test_year_month_only_is_kept_as_first_of_month():
    assert parse_date("2018-12") == "2018-12-01"

def test_zero_and_ancient_dates_are_rejected():
    assert parse_date("0001-01-01T00:00:00Z") is None
    assert parse_date("1970-01-01") is None
    assert parse_date("") is None
    assert parse_date(None) is None
