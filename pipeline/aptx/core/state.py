"""The part of the snapshot store that cannot be fetched again, packed for safe keeping.

Most snapshots are copies of what a source serves today, so losing them costs
a slow re-download and nothing else. Two kinds are different. A blog feed
shows only its newest posts, so the older ones exist only in our earlier
snapshots, and the link check's results take weeks to build up. Both are
small, and neither holds anyone's text: a feed snapshot keeps a title, a link
and a date per post, and the link results map a URL to a status. Everything
else, which includes the raw payloads of the other sources, is never packed.

The allowlist below is the whole rule. `pack` writes only these paths and
`unpack` refuses an archive that holds anything else, so a mistake in the
workflow cannot widen what is stored.
"""
import re
import tarfile
from collections.abc import Collection
from pathlib import Path

from aptx.core.snapshot import SnapshotStore

FEED_FILE = "posts.json"
LINK_FILE = "links/status.json"


def _allowed(feeds: Collection[str]) -> re.Pattern[str]:
    names = "|".join(re.escape(f) for f in sorted(feeds)) or "(?!)"
    return re.compile(rf"(?:(?:{names})/\d{{4}}-\d{{2}}-\d{{2}}/{re.escape(FEED_FILE)}|{re.escape(LINK_FILE)})")


def pack(store: SnapshotStore, archive: Path, feeds: Collection[str]) -> list[str]:
    """Write the newest saved snapshot of each feed, and the link results, to `archive`. Returns the paths."""
    members: list[str] = []
    for name in sorted(feeds):
        # A feed snapshot already holds every post the earlier ones did, so only the newest is kept.
        for d in reversed(store._dated_dirs(name)):
            if (d / FEED_FILE).is_file():
                members.append(f"{name}/{d.name}/{FEED_FILE}")
                break
    if (store.root / LINK_FILE).is_file():
        members.append(LINK_FILE)
    allowed = _allowed(feeds)
    if not all(allowed.fullmatch(m) for m in members):
        raise ValueError(f"refusing to pack a path outside the allowlist: {members}")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "w:gz") as tar:
        for m in members:
            tar.add(store.root / m, arcname=m, recursive=False)
    return members


def unpack(store: SnapshotStore, archive: Path, feeds: Collection[str]) -> list[str]:
    """Restore the files in `archive` into the store, over any older copy. Returns the paths."""
    allowed = _allowed(feeds)
    with tarfile.open(archive, "r:gz") as tar:
        members = tar.getmembers()
        bad = [m.name for m in members if not (m.isfile() and allowed.fullmatch(m.name))]
        if bad:
            raise ValueError(f"{archive} holds files that are not saved state: {', '.join(bad[:5])}")
        tar.extractall(store.root, members=members, filter="data")
    return [m.name for m in members]
