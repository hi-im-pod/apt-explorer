"""What every connector shares: the Connector protocol, timestamps, and the
licence gate read from SOURCES.md."""
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable

from aptx.core.models import SourceBundle
from aptx.core.snapshot import SnapshotStore

log = logging.getLogger(__name__)

# base.py sits at pipeline/aptx/sources/, so parents[3] is the repository root.
SOURCES_MD = Path(__file__).resolve().parents[3] / "SOURCES.md"

PUBLISH_VALUES = frozenset({"full", "derived-only", "evidence-only", "link-only"})
# The most restrictive value is the default. A source whose terms were never
# recorded is used for resolution evidence only, and nothing from it is
# published.
DEFAULT_POLICY = "evidence-only"


@runtime_checkable
class Connector(Protocol):
    """One source. fetch() stores raw payloads, and normalize() reads them back.

    The two steps are separate so a failed fetch can still normalize the last
    good snapshot. A connector that needs another source's data, such as ORKL
    needing Malpedia's library dates, takes it as extra parameters on
    normalize(), and the CLI passes it in. Connectors never import each other.

    Connectors subclass this protocol explicitly, so they inherit policy().
    Structural typing alone would not hand them the default body.
    """
    name: str

    def fetch(self, store: SnapshotStore) -> None: ...

    def normalize(self, store: SnapshotStore) -> SourceBundle: ...

    def policy(self, store: SnapshotStore, sources_md: Path | None = None) -> str:
        """What may be published from this source, by SOURCES.md.

        The CLI and assembly ask each connector, never publish_policy(name)
        directly, so a connector can add its own checks. ETDA overrides this
        with a licence drift check, which a direct publish_policy("etda")
        call would silently skip. The store is a parameter for that reason;
        the default ignores it.
        """
        return publish_policy(self.name, sources_md)


def now_iso() -> str:
    """The current UTC time as YYYY-MM-DDTHH:MM:SSZ.

    Use it for retrieved_at only when the data was fetched in this run. A
    connector that normalizes an older snapshot, for example after a failed
    fetch, should stamp the snapshot's date from store.latest_date(source).
    Otherwise stale data would claim to be fresh.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_UNESCAPED_PIPE = re.compile(r"(?<!\\)\|")
_SEPARATOR_CELL = re.compile(r":?-+:?")
_BACKTICKED = re.compile(r"`([^`]+)`")


def _cells(line: str) -> list[str]:
    # Licence quotes can contain a pipe, which Markdown writes as \|. Only an
    # unescaped pipe separates cells.
    inner = line.strip()
    inner = inner[1:] if inner.startswith("|") else inner
    inner = inner[:-1] if inner.endswith("|") and not inner.endswith("\\|") else inner
    return [c.strip().replace("\\|", "|") for c in _UNESCAPED_PIPE.split(inner)]


def _plain(cell: str) -> str:
    return cell.strip().strip("*`").strip().casefold()


def _names_source(cell: str, name: str) -> bool:
    # A row's first cell is a human name such as "MITRE ATT&CK", which never
    # equals the connector key "attack". SOURCES.md therefore carries the key
    # in backticks, and only that key or a bare-key cell counts as a match.
    # Fuzzy matching could open the gate for the wrong source.
    key = name.casefold()
    return key in (k.strip().casefold() for k in _BACKTICKED.findall(cell)) or _plain(cell) == key


def publish_policy(name: str, path: Path | None = None) -> str:
    """What SOURCES.md allows us to publish from source `name`.

    The function reads the `publish` column of the row whose first cell names
    the source, as ``Title (`key`)`` or as the bare key. It returns
    "evidence-only" when the file, the row or a recognised value is missing.
    This is the licence gate, so any doubt keeps the data out of data/.
    """
    path = SOURCES_MD if path is None else Path(path)
    try:
        # utf-8-sig accepts a byte order mark from Windows editors, and an
        # explicit codec stops a non-UTF-8 system locale from misreading © and ®.
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        log.warning("publish policy for %r: cannot read %s (%s); using %s", name, path, e, DEFAULT_POLICY)
        return DEFAULT_POLICY

    col: int | None = None
    for line in lines:
        if not line.strip().startswith("|"):
            col = None          # Any non-table line ends the current table.
            continue
        cells = _cells(line)
        plain = [_plain(c) for c in cells]
        if "publish" in plain:
            col = plain.index("publish")
            continue
        if col is None or all(_SEPARATOR_CELL.fullmatch(c) for c in cells):
            continue
        if cells and _names_source(cells[0], name) and col < len(cells):
            value = _plain(cells[col])
            if value in PUBLISH_VALUES:
                return value
            log.warning("publish policy for %r: unrecognised value %r in %s; using %s",
                        name, cells[col], path, DEFAULT_POLICY)
            return DEFAULT_POLICY

    log.warning("publish policy for %r: no row in %s; using %s", name, path, DEFAULT_POLICY)
    return DEFAULT_POLICY
