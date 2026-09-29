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


# A month or day that does not exist would otherwise reach a year shard or a
# chart axis as a date no calendar has, so parse_date treats it as unusable.
def test_a_day_that_does_not_exist_is_rejected():
    assert parse_date("2024-02-30") is None
    assert parse_date("2023-02-29") is None     # 2023 is not a leap year.
    assert parse_date("2024-04-31") is None
    assert parse_date("2024-02-30T12:00:00Z") is None

def test_a_month_that_does_not_exist_is_rejected():
    assert parse_date("2024-13-01") is None
    assert parse_date("2024-00-10") is None
    assert parse_date("2024-13") is None
    assert parse_date("2024-00") is None

def test_a_day_of_zero_is_rejected():
    assert parse_date("2024-05-00") is None

def test_leap_day_is_valid():
    assert parse_date("2024-02-29") == "2024-02-29"
    assert parse_date("2024-02-29T23:59:59Z") == "2024-02-29"

def test_last_days_of_each_month_length_are_valid():
    assert parse_date("2024-01-31") == "2024-01-31"
    assert parse_date("2024-04-30") == "2024-04-30"
    assert parse_date("2023-02-28") == "2023-02-28"
