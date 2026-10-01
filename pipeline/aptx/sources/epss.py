"""FIRST's Exploit Prediction Scoring System (EPSS).

EPSS scores are free to use if they are credited. The site shows each score
next to the CVEs that KEV or a report already names. The file holds every CVE
ever scored, so this connector never adds a CVE of its own; assembly only
attaches a score to a CVE that is already on the page.
"""
import csv
import gzip
import io
import logging
import re

from aptx.core import http
from aptx.core.models import SourceBundle, VulnRecord
from aptx.core.snapshot import SnapshotStore
from aptx.sources.base import Connector

log = logging.getLogger(__name__)

EPSS_URL = "https://epss.empiricalsecurity.com/epss_scores-current.csv.gz"
SNAPSHOT = "epss_scores.csv.gz"

_CVE = re.compile(r"CVE-[0-9]{4}-[0-9]{4,7}")
# The live file has well over 300,000 rows. A short file is a failed export,
# and it must never become the newest snapshot.
MIN_ROWS = 100_000


def _rows(payload: bytes) -> list[tuple[str, float, float]]:
    """The valid (cve, score, percentile) rows, or ValueError for a broken file.

    The first line is a comment that names the model and the scoring date. The
    second is the header. A row with a malformed CVE or a value outside 0 to 1
    is dropped and counted, so a change in the feed shows up in the build log.
    """
    text = gzip.decompress(payload).decode("utf-8-sig")
    lines = io.StringIO(text)
    first = lines.readline()
    if not first.startswith("#"):
        raise ValueError("EPSS file does not start with its comment line")
    reader = csv.reader(lines)
    if next(reader, None) != ["cve", "epss", "percentile"]:
        raise ValueError("EPSS file has an unexpected header")
    rows: list[tuple[str, float, float]] = []
    dropped = 0
    for row in reader:
        try:
            cve, score, percentile = row[0].strip().upper(), float(row[1]), float(row[2])
        except (IndexError, ValueError):
            dropped += 1
            continue
        if _CVE.fullmatch(cve) and 0 <= score <= 1 and 0 <= percentile <= 1:
            rows.append((cve, score, percentile))
        else:
            dropped += 1
    if len(rows) < MIN_ROWS:
        raise ValueError(f"EPSS file has only {len(rows)} valid rows")
    if dropped:
        log.warning("epss: dropped %d malformed rows", dropped)
    return rows


class EpssConnector(Connector):
    name = "epss"

    def fetch(self, store: SnapshotStore) -> None:
        payload = http.get_bytes(EPSS_URL)
        _rows(payload)
        store.save(self.name, SNAPSHOT, payload)

    def normalize(self, store: SnapshotStore) -> SourceBundle:
        raw = store.latest(self.name, SNAPSHOT)
        if raw is None:
            return SourceBundle(source=self.name)
        retrieved_at = store.latest_date(self.name)
        seen: dict[str, VulnRecord] = {}
        for cve, score, percentile in _rows(raw):
            if cve not in seen:
                seen[cve] = VulnRecord.model_construct(
                    cve=cve, kev_date_added=None, ransomware=None, vendor=None, product=None,
                    epss=score, epss_percentile=percentile, retrieved_at=retrieved_at)
        return SourceBundle(source=self.name, vulns=list(seen.values()))
