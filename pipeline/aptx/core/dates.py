import re
from datetime import date

from aptx.core.urls import norm_url

_ISO = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?")

def parse_date(s: str | None) -> str | None:
    """Return YYYY-MM-DD, or None for missing, zero, pre-1990 or impossible dates.

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
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3) or 1)
    if year < 1990:
        return None
    # The regex only checks digit counts, so 2024-02-30 and 2024-13-01 get here.
    # Building a real date rejects them, and leap days come out right for free.
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


# VX-Underground files its papers as "YYYY-MM-DD - Title", and ORKL copies that file name into the
# title. The text after the dash is the paper's title.
_TITLE_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+[-–—]\s+(\S.*)$")


def split_title_date(title: str) -> tuple[str, str | None]:
    """A title without its filing-date prefix, and that prefix as a date when it is a real one.

    The prefix is filing noise even when the date is nonsense, so it always leaves the title. Only a
    date that parse_date accepts is returned, because a typo must not date the report.
    """
    title, first = title.strip(), None
    # A few papers are filed as "DATE - DATE - Title", so the prefix comes off until none is left.
    # The outermost date is kept, because it is the one the collection filed the paper under.
    while m := _TITLE_DATE.match(title):
        title = m.group(2)
        first = first or parse_date(m.group(1))
    return title, first


def resolve_report_date(urls: list[str], lib_dates: dict[str, str], file_creation: str | None,
                        created_at: str | None, title_date: str | None = None) -> tuple[str | None, str]:
    """A report's date and the basis it came from, best evidence first.

    1. The Malpedia library date of the first URL found in lib_dates, which
       maps norm_url(url) to YYYY-MM-DD ("malpedia-library").
    2. The date in the title's own filing prefix ("title-date"). It beats the
       file metadata because that metadata is often years off for the papers
       that carry such a prefix. It is trusted only when it is no later than
       the ingest date, since a report cannot be published after ORKL saw it.
    3. The report file's own creation date ("file-metadata").
    4. The date ORKL ingested the report ("orkl-ingest"). That is when ORKL
       saw it, not when it was published, so the basis says so.
    5. Nothing usable: (None, "unknown"). Such a report goes to
       reports/undated.json and stays out of dated trends.

    Every candidate goes through parse_date, so a sentinel such as ORKL's
    0001-01-01 falls through to the next basis instead of landing in year 1.
    """
    for url in urls:
        if url:
            date = parse_date(lib_dates.get(norm_url(url)))
            if date:
                return date, "malpedia-library"
    ingest = parse_date(created_at)
    date = parse_date(title_date)
    if date and (ingest is None or date <= ingest):
        return date, "title-date"
    date = parse_date(file_creation)
    if date:
        return date, "file-metadata"
    if ingest:
        return ingest, "orkl-ingest"
    return None, "unknown"
