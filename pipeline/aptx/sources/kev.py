"""CISA's Known Exploited Vulnerabilities catalogue.

KEV is CC0, so every field taken here may be published. The site uses it for
the date each CVE was added and for CISA's known-ransomware flag.
"""
import json
import logging
import re

from aptx.core import http
from aptx.core.dates import parse_date
from aptx.core.models import SourceBundle, VulnRecord
from aptx.core.snapshot import SnapshotStore

log = logging.getLogger(__name__)

KEV_URL = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
SNAPSHOT = "known_exploited_vulnerabilities.json"

_CVE = re.compile(r"CVE-[0-9]{4}-[0-9]{4,7}")
# KEV answers "Known" or "Unknown". Anything else, including a missing field,
# means the catalogue does not say, which the contract records as null.
_RANSOMWARE = {"known": True, "unknown": False}


def _vulnerabilities(payload: bytes) -> list:
    """The catalogue's vulnerability list, or ValueError when there is none.

    A 200 response can still carry a maintenance page or an empty list. Such a
    payload must never become the newest snapshot, because the source would
    then look fresh while publishing nothing.
    """
    data = json.loads(payload.decode("utf-8-sig"))
    vulns = data.get("vulnerabilities") if isinstance(data, dict) else None
    if not isinstance(vulns, list) or not vulns:
        raise ValueError("KEV catalogue has no vulnerabilities")
    return vulns


def _label(value) -> str | None:
    # The live catalogue pads some vendor and product names with spaces, and
    # published labels must be trimmed single lines.
    text = " ".join(str(value).split()) if value is not None else ""
    return text or None


class KevConnector:
    name = "kev"

    def fetch(self, store: SnapshotStore) -> None:
        payload = http.get_bytes(KEV_URL)
        _vulnerabilities(payload)
        store.save(self.name, SNAPSHOT, payload)

    def normalize(self, store: SnapshotStore) -> SourceBundle:
        raw = store.latest(self.name, SNAPSHOT)
        if raw is None:
            return SourceBundle(source=self.name)
        # The records are only as fresh as the snapshot. After a failed fetch
        # that snapshot is older than today, and the date must say so.
        retrieved_at = store.latest_date(self.name)
        vulns: dict[str, VulnRecord] = {}
        dropped: list[str] = []
        for item in _vulnerabilities(raw):
            cve = str(item.get("cveID") or "").strip().upper()
            if not _CVE.fullmatch(cve):
                dropped.append(repr(item.get("cveID")))
                continue
            if cve in vulns:
                continue
            flag = str(item.get("knownRansomwareCampaignUse") or "").strip().casefold()
            vulns[cve] = VulnRecord(
                cve=cve,
                kev_date_added=parse_date(item.get("dateAdded")),
                ransomware=_RANSOMWARE.get(flag),
                vendor=_label(item.get("vendorProject")),
                product=_label(item.get("product")),
                retrieved_at=retrieved_at,
            )
        if dropped:
            # Malformed records are dropped one by one and counted, never
            # silently, so a change in the feed shows up in the build log.
            log.warning("kev: dropped %d records with a malformed CVE ID: %s",
                        len(dropped), ", ".join(dropped[:10]))
        return SourceBundle(source=self.name, vulns=list(vulns.values()))
