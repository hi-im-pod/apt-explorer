import re

_ISO = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?")

def parse_date(s: str | None) -> str | None:
    """Return YYYY-MM-DD, or None for missing, zero or pre-1990 values.

    Sources use sentinel dates (ORKL's 0001-01-01, epoch zero) for "unknown";
    treating those as real would put reports in year 1 on every chart.
    """
    if not s:
        return None
    m = _ISO.match(s.strip())
    if not m:
        return None
    # A source that gives only year and month still places the report in the
    # right month and quarter, so the first of the month stands in for the day.
    year, month, day = int(m.group(1)), m.group(2), m.group(3) or "01"
    if year < 1990:
        return None
    return f"{year:04d}-{month}-{day}"
