"""The dataset released with Yuldoshkhujaev et al., CCS '25 (Zenodo 16869733).

The dataset is CC BY 4.0 and appears on the site only as an attributed
historical layer of 2014–2023 reports; no trend is computed from it. Two
files are kept: Information_Retrieved_Collection.csv, one row per report, and
Threat_Actor_Collection.csv, the paper's own actor list. The actor list is not
published. It is kept so the registry evaluation can find the report actor
names that the paper itself left unresolved.
"""
import csv
import io
import logging
import re
from urllib.parse import quote

from aptx.core import http
from aptx.core.dates import parse_date
from aptx.core.models import ReportRecord, SourceBundle
from aptx.core.snapshot import SnapshotStore
from aptx.sources.base import Connector

log = logging.getLogger(__name__)

_RECORD = "https://zenodo.org/api/records/16869733/files"
REPORTS_URL = f"{_RECORD}/Information_Retrieved_Collection.csv/content"
ACTORS_URL = f"{_RECORD}/Threat_Actor_Collection.csv/content"
REPORTS_SNAPSHOT = "Information_Retrieved_Collection.csv"
ACTORS_SNAPSHOT = "Threat_Actor_Collection.csv"

# Only the columns the pipeline reads are required, so a column the pipeline
# ignores can come or go without failing the fetch.
REPORT_COLUMNS = ("Date", "Filename", "Title", "Download_url", "Source", "CVE", "MITRE_ID", "Threat_actor")
ACTOR_COLUMNS = ("Threat Actor", "Other Names")

# The contract's URL pattern is case-sensitive, so the scheme is lowered on
# the way in; HTTP:// would otherwise fail schema validation at build time.
_HTTP_URL = re.compile(r"(https?)(://\S+)", re.IGNORECASE)
_CVE = re.compile(r"CVE-[0-9]{4}-[0-9]{4,7}")
# ATT&CK Enterprise technique IDs all start with T1. The dataset's MITRE_ID
# column also holds tactic IDs (TA0001), software IDs (S0063) and malware
# names that look like IDs (T9000, T5000), and none of those are techniques.
_TECHNIQUE = re.compile(r"T1[0-9]{3}(\.[0-9]{3})?")
# The real data writes some CVE IDs with Unicode hyphens (U+2011, U+2013),
# which would fail the contract's pattern and never match KEV.
_HYPHENS = str.maketrans({c: "-" for c in "‐‑‒–—―−"})
# Filenames contain spaces, and report IDs must not. Percent-encoding every
# character outside this set, "%" included, keeps each ID readable, traceable
# to its row and distinct: two real Filenames differ only in doubled spaces.
_ID_SAFE = "!$&'()*+,;=:@"


def _text(value) -> str:
    """The value as one trimmed line, or "" when empty or "Not mentioned".

    "Not mentioned" is the dataset's marker for a missing value, not a value.
    """
    text = " ".join(str(value or "").split())
    return "" if text.casefold() == "not mentioned" else text


def _parts(value) -> list[str]:
    # Multi-valued cells are comma-separated with irregular spacing, such as
    # "apt29, apt28" and " apt28". Order is kept and repeats are dropped.
    seen: dict[str, None] = {}
    for part in str(value or "").split(","):
        text = _text(part)
        if text:
            seen.setdefault(text, None)
    return list(seen)


def _cves(value) -> list[str]:
    # Truncated IDs such as CVE-2012-015 name no CVE and are dropped.
    found = {p.translate(_HYPHENS).upper() for p in _parts(value)}
    return sorted(c for c in found if _CVE.fullmatch(c))


def _techniques(value) -> list[str]:
    # Each entry reads "T1059:Command-Line Interface" or "T1566:N/A". Only the
    # ID before the colon is kept; ATT&CK itself supplies the names.
    ids = {p.split(":", 1)[0].strip() for p in _parts(value)}
    return sorted(i for i in ids if _TECHNIQUE.fullmatch(i))


def _rows(payload: bytes, required: tuple[str, ...], what: str) -> list[dict]:
    """The CSV's rows, or ValueError when the file is not the expected table.

    A 200 response can carry an error page or a truncated file. Such a payload
    must never become the newest snapshot, because the source would then look
    fresh while publishing nothing.
    """
    try:
        # utf-8-sig accepts a byte order mark, and newline="" keeps line breaks
        # inside quoted cells, which the csv module then reads as one cell.
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline=""))
        rows = list(reader)
    except (UnicodeDecodeError, csv.Error) as e:
        raise ValueError(f"paper: {what} is not a readable CSV ({e})") from e
    missing = [c for c in required if c not in (reader.fieldnames or [])]
    if missing:
        raise ValueError(f"paper: {what} lacks the columns {', '.join(missing)}")
    if not rows:
        raise ValueError(f"paper: {what} has no rows")
    return rows


def _latest_rows(store: SnapshotStore, name: str, required: tuple[str, ...]) -> list[dict] | None:
    raw = store.latest("paper", name)
    return None if raw is None else _rows(raw, required, name)


def report_actor_names(store: SnapshotStore) -> list[str]:
    """Every distinct Threat_actor name across the report rows, sorted.

    These are the names the registry is measured against: the full real file
    gives 443, the denominator of paper_match in resolution.json. The names
    are verbatim apart from trimming, and "Not mentioned" is not a name.
    """
    rows = _latest_rows(store, REPORTS_SNAPSHOT, REPORT_COLUMNS) or []
    names = {n for r in rows for n in _parts(r.get("Threat_actor"))}
    return sorted(names, key=lambda n: (n.casefold(), n))


def unresolved_actor_names(store: SnapshotStore) -> list[str]:
    """The report actor names that the paper's own actor list does not contain.

    A name resolves when it equals, ignoring case, an actor's "Threat Actor"
    or one of its comma-separated "Other Names". Against the real files this
    rule gives 130 of 443, the figure the spec quotes, and these names seed
    the labelled set for the registry evaluation. Raises LookupError when
    either snapshot is missing, because an empty answer would read as "every
    name resolved".
    """
    reports = _latest_rows(store, REPORTS_SNAPSHOT, REPORT_COLUMNS)
    actors = _latest_rows(store, ACTORS_SNAPSHOT, ACTOR_COLUMNS)
    if reports is None or actors is None:
        raise LookupError("paper: both dataset files are needed; run fetch first")
    known = set()
    for a in actors:
        known.update(n.casefold() for n in [_text(a.get("Threat Actor")), *_parts(a.get("Other Names"))] if n)
    return [n for n in report_actor_names(store) if n.casefold() not in known]


class PaperConnector(Connector):
    name = "paper"

    def fetch(self, store: SnapshotStore) -> None:
        reports = http.get_bytes(REPORTS_URL)
        _rows(reports, REPORT_COLUMNS, REPORTS_SNAPSHOT)
        actors = http.get_bytes(ACTORS_URL)
        _rows(actors, ACTOR_COLUMNS, ACTORS_SNAPSHOT)
        # Both files are checked before either is saved, so the pair on disk
        # always comes from the same fetch.
        store.save(self.name, REPORTS_SNAPSHOT, reports)
        store.save(self.name, ACTORS_SNAPSHOT, actors)

    def normalize(self, store: SnapshotStore) -> SourceBundle:
        rows = _latest_rows(store, REPORTS_SNAPSHOT, REPORT_COLUMNS)
        if rows is None:
            return SourceBundle(source=self.name)
        # The records are only as fresh as the snapshot, which is older than
        # today when this week's fetch failed.
        retrieved_at = store.latest_date(self.name)
        reports: dict[str, ReportRecord] = {}
        no_filename = repeated = 0
        for r in rows:
            filename = str(r.get("Filename") or "")
            if not filename.strip():
                no_filename += 1
                continue
            # The Filename is the dataset's own key for a row, so the ID is
            # built from it and can be traced back to the file.
            sid = quote(filename, safe=_ID_SAFE)
            if sid in reports:
                repeated += 1
                continue
            published = parse_date(_text(r.get("Date")))
            link = _HTTP_URL.fullmatch(_text(r.get("Download_url")))
            url = link.group(1).lower() + link.group(2) if link else None
            reports[sid] = ReportRecord(
                source=self.name,
                source_id=sid,
                # Most rows have no Title, and the Filename is then the only
                # name the row has.
                title=_text(r.get("Title")) or _text(filename),
                published=published,
                # The contract ties a null date to the "unknown" basis, so a
                # row without a usable date does not claim the paper dated it.
                date_basis="paper" if published else "unknown",
                organisation=_text(r.get("Source")) or None,
                url=url,
                actor_names=_parts(r.get("Threat_actor")),
                cves=_cves(r.get("CVE")),
                techniques=_techniques(r.get("MITRE_ID")),
                retrieved_at=retrieved_at,
            )
        if no_filename or repeated:
            # Malformed rows are dropped one by one and counted, never
            # silently, so a change in the dataset shows up in the build log.
            log.warning("paper: dropped %d rows (%d without a Filename, %d repeating one)",
                        no_filename + repeated, no_filename, repeated)
        return SourceBundle(source=self.name, reports=list(reports.values()))
