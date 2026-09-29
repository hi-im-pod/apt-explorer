import os
from datetime import datetime, timezone
from pathlib import Path

class ShrunkSnapshotError(RuntimeError):
    """A new payload is suspiciously small next to the last good one."""

def default_root() -> Path:
    # The repository is public, so raw payloads live in a gitignored folder at
    # the repo root. APTX_CACHE moves them elsewhere, for example the Actions
    # cache or one shared folder for several worktrees.
    return Path(os.environ.get("APTX_CACHE", Path(__file__).resolve().parents[3] / ".cache" / "snapshots"))

class SnapshotStore:
    """Dated raw payloads per source, kept outside git.

    A source that answers 200 with an empty or truncated body is the failure
    this guards against: the last good snapshot must survive it.
    """
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else default_root()

    def _dir(self, source: str) -> Path:
        return self.root / source

    def save(self, source: str, name: str, payload: bytes, min_ratio: float = 0.5) -> Path:
        prev = self.latest(source, name)
        # The check runs before anything touches disk, so a refused payload
        # never replaces the last good one, even when both fall on the same day.
        if prev is not None and len(prev) > 0 and len(payload) < len(prev) * min_ratio:
            raise ShrunkSnapshotError(f"{source}/{name}: {len(payload)} bytes vs {len(prev)} last time")
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        d = self._dir(source) / stamp
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        p.write_bytes(payload)
        return p

    def _dated_dirs(self, source: str) -> list[Path]:
        # Folder names are YYYY-MM-DD, so sorting them as text also sorts them
        # by date.
        d = self._dir(source)
        return sorted([p for p in d.iterdir() if p.is_dir()]) if d.exists() else []

    def latest(self, source: str, name: str) -> bytes | None:
        # Walk back through the dates because one run may save only some of a
        # source's files. The newest copy of this file may be older than the
        # newest folder.
        for d in reversed(self._dated_dirs(source)):
            if (d / name).exists():
                return (d / name).read_bytes()
        return None

    def latest_date(self, source: str) -> str | None:
        dirs = self._dated_dirs(source)
        return dirs[-1].name if dirs else None
