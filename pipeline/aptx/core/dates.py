import re

from aptx.core.urls import norm_url

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


def resolve_report_date(urls: list[str], lib_dates: dict[str, str], file_creation: str | None,
                        created_at: str | None) -> tuple[str | None, str]:
    """A report's date and the basis it came from, best evidence first.

    1. The Malpedia library date of the first URL found in lib_dates, which
       maps norm_url(url) to YYYY-MM-DD ("malpedia-library").
    2. The report file's own creation date ("file-metadata").
    3. The date ORKL ingested the report ("orkl-ingest"). That is when ORKL
       saw it, not when it was published, so the basis says so.
    4. Nothing usable: (None, "unknown"). Such a report goes to
       reports/undated.json and stays out of dated trends.

    Every candidate goes through parse_date, so a sentinel such as ORKL's
    0001-01-01 falls through to the next basis instead of landing in year 1.
    """
    for url in urls:
        if url:
            date = parse_date(lib_dates.get(norm_url(url)))
            if date:
                return date, "malpedia-library"
    date = parse_date(file_creation)
    if date:
        return date, "file-metadata"
    date = parse_date(created_at)
    if date:
        return date, "orkl-ingest"
    return None, "unknown"
