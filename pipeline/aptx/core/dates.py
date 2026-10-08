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


# A blog post's address often carries its publication date: /2021/05/31/slug or /2021/05/slug.
_URL_DATE = re.compile(r"/((?:19|20)\d{2})/(0[1-9]|1[0-2])(?:/(0[1-9]|[12]\d|3[01]))?(?=/|$|[?#])")
# Under an upload or media folder the date is when a file was uploaded, which can be long after
# the report it belongs to, so such a path gives no date.
_UPLOAD_PATH = re.compile(r"/(?:wp-content|uploads?|media|files|assets|images?|img|static|download)/", re.I)
_WAYBACK = re.compile(r"^https?://web\.archive\.org/web/(\d{4})(\d{2})(\d{2})", re.I)
# A library date this much earlier than the date in the report's own address is taken to be a
# wrong year in the library, not an early copy.
URL_OVERRIDES_LIBRARY_DAYS = 365


def url_date(url: str | None) -> str | None:
    """The publication date in a blog-style address, or None.

    A Wayback Machine address is read for the original address it wraps, since the capture
    time is not the publication date (see wayback_date).
    """
    if not url:
        return None
    path = re.sub(r"^https?://web\.archive\.org/web/\d+[a-z_]*/", "", url, flags=re.I)
    path = re.sub(r"^https?://[^/]+", "", path)
    if _UPLOAD_PATH.search(path):
        return None
    m = _URL_DATE.search(path)
    if not m:
        return None
    return parse_date(f"{m.group(1)}-{m.group(2)}-{m.group(3) or '01'}")


def wayback_date(url: str | None) -> str | None:
    """The day the Wayback Machine captured the page, which the report cannot postdate."""
    m = _WAYBACK.match(url or "")
    return parse_date(f"{m.group(1)}-{m.group(2)}-{m.group(3)}") if m else None


def _days_between(earlier: str, later: str) -> int:
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def resolve_report_date(urls: list[str], lib_dates: dict[str, str], file_creation: str | None,
                        created_at: str | None, title_date: str | None = None) -> tuple[str | None, str]:
    """A report's date and the basis it came from, best evidence first.

    1. The Malpedia library date of the first URL found in lib_dates, which
       maps norm_url(url) to YYYY-MM-DD ("malpedia-library"), unless the
       report's own address carries a date at least URL_OVERRIDES_LIBRARY_DAYS
       later: then the library has the year wrong and the address wins.
    2. The date in the title's own filing prefix ("title-date"). It beats the
       file metadata because that metadata is often years off for the papers
       that carry such a prefix. It is trusted only when it is no later than
       the ingest date, since a report cannot be published after ORKL saw it.
    3. The date in the report's address, such as /2021/05/31/ ("url-date"),
       on the same no-later-than-ingest condition.
    4. The report file's own creation date ("file-metadata").
    5. The day a Wayback Machine address captured the page ("wayback-capture").
       The report existed by then, so it is an upper bound, closer than the
       ingest date.
    6. The date ORKL ingested the report ("orkl-ingest"). That is when ORKL
       saw it, not when it was published, so the basis says so, and trends
       leave such reports out.
    7. Nothing usable: (None, "unknown"). Such a report goes to
       reports/undated.json and stays out of dated trends.

    Every candidate goes through parse_date, so a sentinel such as ORKL's
    0001-01-01 falls through to the next basis instead of landing in year 1.
    """
    ingest = parse_date(created_at)
    no_later_than_ingest = lambda d: d and (ingest is None or d <= ingest)
    in_url = next((d for u in urls if no_later_than_ingest(d := url_date(u))), None)
    for url in urls:
        if url:
            date_ = parse_date(lib_dates.get(norm_url(url)))
            if date_:
                if in_url and _days_between(date_, in_url) >= URL_OVERRIDES_LIBRARY_DAYS:
                    return in_url, "url-date"
                return date_, "malpedia-library"
    date_ = parse_date(title_date)
    if no_later_than_ingest(date_):
        return date_, "title-date"
    if in_url:
        return in_url, "url-date"
    date_ = parse_date(file_creation)
    if date_:
        return date_, "file-metadata"
    captured = next((d for u in urls if no_later_than_ingest(d := wayback_date(u))), None)
    if captured:
        return captured, "wayback-capture"
    if ingest:
        return ingest, "orkl-ingest"
    return None, "unknown"
