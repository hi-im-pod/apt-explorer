"""The command line: `python -m aptx run` builds data/, `python -m aptx links` checks report links.

This module is the only place that knows the sources as a group. Every
connector stays ignorant of the others, so the wiring between them lives
here: which sources exist, what each may publish, what ORKL needs from ATT&CK
and Malpedia, and what a failed fetch does to a build.

A failed fetch never fails the build. The source's last good snapshot is
still normalized and published, and the source is marked stale so a reader can
see the data is old. The build fails only when the assembled output breaks the
data contract, and then nothing is written, so the previous data/ stays.
"""
import argparse
import hashlib
import json
import logging
import os
import sys
import threading
import time
from collections import Counter
from collections.abc import Collection, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from aptx.build import assemble as assembly
from aptx.build import guesses, slugs
from aptx.build.assemble import BuildFacts
from aptx.build.notice import SOURCE_ORDER
from aptx.build.write import WriteRefused, write_all
from aptx.core import http
from aptx.core.models import ActorRecord, SourceBundle
from aptx.core import state as saved_state
from aptx.core.snapshot import SnapshotStore
from aptx.resolve import pairs as name_pairs
from aptx.resolve.names import norm
from aptx.resolve.registry import resolve
from aptx.sources import attack, etda, malpedia, paper
from aptx.sources.attack import AttackConnector
from aptx.sources.base import Connector, now_iso
from aptx.sources.dfir import DfirConnector
from aptx.sources.etda import EtdaConnector
from aptx.sources.epss import EpssConnector
from aptx.sources.feed import FeedConnector
from aptx.sources.kev import KevConnector
from aptx.sources.malpedia import MalpediaConnector
from aptx.sources.microsoft import MicrosoftConnector
from aptx.sources.misp import MispConnector
from aptx.sources.orkl import OrklConnector
from aptx.sources.paper import PaperConnector
from aptx.sources.vendors import EsetConnector, MicrosoftBlogConnector, TalosConnector

log = logging.getLogger("aptx")

# What the site may draw from a source's Malpedia-derived data. An evidence-only
# Malpedia is used for merging actors and nothing else, so its library dates
# and report links must not reach a published report.
_MALPEDIA_SHOWN = frozenset({"full", "derived-only"})

# Written next to the snapshots so that a rebuild with --skip-fetch still
# knows which sources failed to fetch. The weekly workflow rebuilds from the
# snapshots after the link check, and without this file that second build
# would publish a failed source as fresh.
FETCH_STATUS = "fetch-status.json"
LINK_STATUS = Path("links") / "status.json"


def default_connectors() -> list[Connector]:
    """The thirteen sources, listed here and nowhere else, in the order notice.SOURCE_ORDER uses."""
    return [AttackConnector(), MispConnector(), EtdaConnector(), MalpediaConnector(),
            OrklConnector(), KevConnector(), DfirConnector(), PaperConnector(), MicrosoftConnector(),
            EpssConnector(), TalosConnector(), EsetConnector(), MicrosoftBlogConnector()]


# Small JSON files in the snapshot store

def _read_json(path: Path) -> dict:
    # A missing or damaged file means "nothing recorded". Both files are
    # conveniences that a build can do without, so neither may stop a build.
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    # A replace, so an interrupted write never leaves a half-written file behind.
    os.replace(tmp, path)


def load_link_status(store: SnapshotStore) -> dict[str, dict]:
    """The link check's results, a report URL to {ok, status, checked_at}."""
    return {u: r for u, r in _read_json(store.root / LINK_STATUS).items()
            if isinstance(r, dict) and isinstance(r.get("ok"), bool)}


# The build

def _fetch_all(store: SnapshotStore, connectors: Sequence[Connector], only: Collection[str] | None) -> dict[str, dict]:
    """Fetch each selected connector, and return what happened to each one."""
    attempts: dict[str, dict] = {}
    for c in connectors:
        if only is not None and c.name not in only:
            continue
        try:
            c.fetch(store)
        except Exception as e:  # noqa: BLE001 - any failure of one source must leave the others alone
            # ShrunkSnapshotError lands here too: the snapshot store refused a
            # payload that shrank, so the last good snapshot is what we publish.
            log.warning("%s: fetch failed, using the previous snapshot (%s: %s)", c.name, type(e).__name__, e)
            attempts[c.name] = {"ok": False, "at": now_iso(), "error": f"{type(e).__name__}: {e}"[:300]}
        else:
            log.info("%s: fetched", c.name)
            attempts[c.name] = {"ok": True, "at": now_iso(), "error": None}
    return attempts


def _labels(path: Path | None) -> tuple[guesses.Label, ...]:
    """The labelled set that guesses.json is measured on, or nothing when the file is absent.

    A missing file must not stop a build. The guesses are an extra that says what
    unresolved names probably are, and without ground truth they say nothing.
    """
    try:
        return tuple(guesses.read_labels(path or guesses.DEFAULT_LABELS))
    except (OSError, KeyError, ValueError) as e:
        log.warning("guesses: no labelled set, so guesses.json will hold no guesses (%s: %s)", type(e).__name__, e)
        return ()


def _pair_records(decisions: Sequence[name_pairs.Decision], by_pair: dict, lookup, shown: dict[str, str],
                  source: str) -> list[ActorRecord]:
    """One record per accepted pair: a bridge adds an alias under the known actor's own spelling, a new pair names an actor."""
    out = []
    for d in decisions:
        if not d.accepted:
            continue
        known = next((n for n in d.names if lookup(n) in shown), None)
        name, alias = (shown[lookup(known)], next(n for n in d.names if n != known)) if known else (d.primary, d.alias)
        key = ":".join(sorted(norm(n) for n in d.names))
        out.append(ActorRecord(source=source, source_id=f"pair:{key}", name=name, aliases=[alias],
                               retrieved_at=by_pair[key]))
    return out


def _add_vendor_pairs(connectors: Sequence[Connector], store: SnapshotStore, bundles: dict[str, SourceBundle],
                      registry, policies: dict[str, str], labels) -> int:
    """Turn the name pairs vendor posts state into actor records, and return how many were added."""
    shown = {p.id: assembly._display_name(p.members) for p in assembly._published_actors(registry, policies)}
    shown_sources = {k for k, v in policies.items() if v in assembly._SHOWS_FACTS}
    soft = [s for b in bundles.values() for s in b.software]
    ref = guesses.make_reference(registry, soft, [r for b in bundles.values() for r in b.reports if r.source == "paper"],
                                 shown, shown_sources)
    prepared = guesses.prepare(ref, labels, registry.lookup, shown)
    guess = (lambda name: guesses.guess_name(name, 1, prepared)) if prepared else None
    added = 0
    for c in connectors:
        found = getattr(c, "pairs", None)
        if found is None or policies.get(c.name) not in assembly._SHOWS_FACTS:
            continue
        rows = found(store)
        by_pair = {":".join(sorted(norm(n) for n in r["names"])): r["retrieved_at"] for r in rows}
        decisions = name_pairs.select([tuple(r["names"]) for r in rows], registry.lookup, registry.non_actor,
                                      set(shown), guess)
        for d in decisions:
            log.info("%s: pair %s / %s %s (%s)", c.name, *d.names, "added" if d.accepted else "skipped", d.reason)
        records = _pair_records(decisions, by_pair, registry.lookup, shown, c.name)
        if records:
            bundles[c.name] = bundles[c.name].model_copy(update={"actors": [*bundles[c.name].actors, *records]})
            added += len(records)
    return added


def run(out: Path, store: SnapshotStore, connectors: Sequence[Connector] | None = None, fetch: bool = True, *,
        only: Collection[str] | None = None, generated_at: str | None = None,
        slugs_path: Path | None = None,
        labels: Path | None = None) -> dict[str, dict]:
    """Build data/ at `out` and return each source's status.

    `slugs_path` is the slug registry the last build published. It defaults to slugs.json inside
    `out`, which is the committed one when `out` is data/. A build into a scratch directory passes
    the committed file, or the actors would all get first-build slugs.

    `only` limits which sources are fetched; every source is still normalized
    from its newest snapshot. Raises WriteRefused, with nothing written, when the
    output does not pass the contract. Any other exception from a connector's
    normalize() is a bug, not an outage, and is left to stop the build.
    """
    connectors = list(default_connectors() if connectors is None else connectors)
    names = [c.name for c in connectors]
    if len(set(names)) != len(names):
        raise ValueError(f"two connectors share a name: {sorted(n for n in names if names.count(n) > 1)}")

    status_path = store.root / FETCH_STATUS
    recorded = _read_json(status_path)
    attempts: dict[str, dict] = {}

    def fetch_group(group: Sequence[Connector]) -> None:
        attempts.update(_fetch_all(store, group, only))
        if attempts:
            _write_json(status_path, {**recorded, **attempts})

    # ORKL is fetched last. It reads each report's text for the actors it names, and those names are
    # the aliases the other sources publish, so the registry must exist before ORKL's fetch.
    orkl = [c for c in connectors if isinstance(c, OrklConnector)]
    if fetch:
        fetch_group([c for c in connectors if c not in orkl])

    # Asked once per source. ETDA's answer depends on its licence text having
    # not changed, so the CLI never reads SOURCES.md for it directly.
    policies = {c.name: c.policy(store) for c in connectors}
    # A source with no connector is not published from, however the caller got here.
    policies = {key: policies.get(key, "evidence-only") for key in SOURCE_ORDER}

    valid_techniques = attack.technique_ids(store)
    lib_dates = malpedia.library_dates(store) if policies["malpedia"] in _MALPEDIA_SHOWN else {}
    bundles: dict[str, SourceBundle] = {}

    def normalize(c: Connector) -> None:
        if isinstance(c, OrklConnector):
            # ORKL needs ATT&CK's technique set and Malpedia's library dates, and connectors never
            # import each other, so the CLI passes both.
            bundles[c.name] = c.normalize(store, valid_techniques=valid_techniques, lib_dates=lib_dates)
        else:
            bundles[c.name] = c.normalize(store)
        b = bundles[c.name]
        log.info("%s: %d actors, %d reports, %d campaigns, %d vulns, %d software", c.name,
                 len(b.actors), len(b.reports), len(b.campaigns), len(b.vulns), len(b.software))

    for c in connectors:
        if c not in orkl:
            normalize(c)

    # The registry gets every source's records, evidence-only ones included, because merging
    # needs them. Assembly decides what may be shown.
    # BEGIN slugs hook: IDs are frozen against the registry the last build published, and only the
    # sources the policies let a page show may name or anchor an actor.
    generated_at = assembly._timestamp(generated_at)
    previous_slugs = slugs.read_registry(slugs_path if slugs_path is not None else out / "slugs.json")
    shown_sources = slugs.shown_sources(policies)

    def build_registry():
        return resolve([a for b in bundles.values() for a in b.actors],
                       [s for b in bundles.values() for s in b.software],
                       previous_slugs=previous_slugs, shown_sources=shown_sources, build_date=generated_at[:10])

    registry = build_registry()
    # END slugs hook
    # A vendor post that says two names are one adds an alias or an actor, judged against the registry
    # built without it. The second resolve merges the records the first pass allowed.
    if _add_vendor_pairs(connectors, store, bundles, registry, policies, _labels(labels)):
        registry = build_registry()

    if fetch and orkl:
        matcher = assembly.name_matcher(registry, policies)
        for c in orkl:
            c.matcher = matcher
        try:
            fetch_group(orkl)
        finally:
            for c in orkl:
                c.matcher = None
    for c in orkl:
        normalize(c)
    # Reports are grouped in connector order, so the dict is put back in it.
    bundles = {c.name: bundles[c.name] for c in connectors}

    known = {**recorded, **attempts}
    fetch_failed = frozenset(n for n in names if isinstance(known.get(n), dict) and known[n].get("ok") is False)

    facts = BuildFacts(
        copyright_year=attack.copyright_year(store),
        valid_techniques=valid_techniques,
        snapshot_dates={n: store.latest_date(n) for n in SOURCE_ORDER},
        etda_last_db_change=etda.last_db_change(store),
        group_reference_urls=attack.group_reference_urls(store),
        malpedia_report_links=malpedia.report_links(store) if policies["malpedia"] in _MALPEDIA_SHOWN else {},
        paper_names=paper.report_actor_names(store),
        fetch_failed=fetch_failed, guess_labels=_labels(labels))
    link_status = {u: r["ok"] for u, r in load_link_status(store).items()}
    payload = assembly.assemble(bundles, registry, policies, link_status, generated_at, facts=facts)
    write_all(out, payload)

    status = {}
    for row in payload["sources.json"]:
        key = row["name"]
        error = (known.get(key) or {}).get("error") if key in fetch_failed else None
        status[key] = {"stale": row["stale"], "record_count": row["record_count"], "last_success": row["last_success"],
                       "publish": row["publish"], "error": error}
    return status


# The link check

# A server that answers 401, 403 or 429 is there and is only refusing an automated
# client, which is common for vendor blogs behind a bot filter. Calling those links
# dead would send readers to the archive copy of a page that works.
_ALIVE_REFUSALS = frozenset({401, 403, 429})


def _status_ok(status: int) -> bool:
    return status < 400 or status in _ALIVE_REFUSALS


def report_urls(data_dir: Path) -> list[str]:
    """Every distinct original URL in the published report shards."""
    urls: set[str] = set()
    for shard in sorted((Path(data_dir) / "reports").glob("*.json")):
        if shard.name == "index.json":
            continue
        for row in json.loads(shard.read_text(encoding="utf-8")):
            if row.get("url"):
                urls.add(row["url"])
    return sorted(urls)


# One run's limits. There are about 30,000 published links and one host, the VX Underground
# mirror, holds a third of them. Each host is asked once a second at most (http.MIN_INTERVAL),
# so the per-host cap is what keeps one publisher from setting how long the run takes, and the
# time budget is what keeps the run well under the job's own limit.
LINK_SAMPLE = 8000
LINKS_PER_HOST = 1000
LINK_WORKERS = 16
LINK_MINUTES = 40.0


def _host(url: str) -> str:
    return urlsplit(url).netloc.lower()


def plan_link_check(urls: Iterable[str], results: dict, sample: int, per_host: int) -> list[str]:
    """The URLs to check this run, oldest-checked first, at most `per_host` for any one host.

    Never-checked URLs sort first, so successive weeks rotate through every published link.
    A URL skipped for its host's cap keeps its place in line for the next run.
    """
    # An empty checked_at sorts before any timestamp, which is what puts unchecked URLs first.
    def last_checked(u: str) -> str:
        r = results.get(u)
        return str(r.get("checked_at") or "") if isinstance(r, dict) else ""
    # Ties, which are every URL on the first run, are broken by a hash of the URL. Sorting them
    # alphabetically would spend the whole sample on a few hosts, while a hash spreads the sample
    # across hosts and stays repeatable.
    ordered = sorted(set(urls), key=lambda u: (last_checked(u), hashlib.sha1(u.encode("utf-8")).hexdigest()))
    taken: Counter[str] = Counter()
    todo: list[str] = []
    for u in ordered:
        if len(todo) >= max(sample, 0):
            break
        h = _host(u)
        if taken[h] >= per_host:
            continue
        taken[h] += 1
        todo.append(u)
    return todo


def check_links(store: SnapshotStore, urls: Iterable[str], sample: int = LINK_SAMPLE, *, now: str | None = None,
                per_host: int = LINKS_PER_HOST, workers: int = LINK_WORKERS,
                minutes: float | None = LINK_MINUTES) -> dict[str, dict]:
    """Check a sample of URLs and merge the results into the stored ones.

    Hosts run side by side, one thread per host, so each host still sees a single polite
    stream (http.probe waits out the per-host pause) while a slow host does not hold up
    the rest. After `minutes` no new URL is started, and the ones left over stay unchecked
    and sort first next time. Earlier results for other URLs are kept.
    """
    now = now or now_iso()
    path = store.root / LINK_STATUS
    results = _read_json(path)
    todo = plan_link_check(urls, results, sample, per_host)

    by_host: dict[str, list[str]] = {}
    for u in todo:
        by_host.setdefault(_host(u), []).append(u)
    # The longest queues start first, so the run does not end waiting on one big host.
    queues = sorted(by_host.values(), key=len, reverse=True)

    deadline = None if minutes is None else time.monotonic() + minutes * 60
    lock = threading.Lock()
    done: set[str] = set()

    def check_host(queue: list[str]) -> None:
        for url in queue:
            if deadline is not None and time.monotonic() >= deadline:
                return
            try:
                code = http.probe(url)
                entry = {"ok": _status_ok(code), "status": code, "checked_at": now}
            except Exception as e:  # noqa: BLE001 - one bad URL must not end the check
                # The exception's name says what went wrong, such as ConnectTimeout.
                entry = {"ok": False, "status": type(e).__name__, "checked_at": now}
            with lock:
                results[url] = entry
                done.add(url)
                if len(done) % 100 == 0:
                    # Saved as it goes, because a full run takes a while and may be cut off.
                    _write_json(path, results)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        list(pool.map(check_host, queues))
    _write_json(path, results)
    left = len(todo) - len(done)
    if left:
        log.warning("links: stopped at the %s-minute budget with %d of %d planned URLs unchecked", minutes, left, len(todo))
    log.info("links: checked %d across %d hosts, %d not ok", len(done), len(queues),
             sum(1 for u in done if not results[u]["ok"]))
    return {u: results[u] for u in todo if u in done}


# Entry point

def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aptx", description="Build the APT Explorer data.")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="fetch the sources and write data/")
    r.add_argument("--out", type=Path, default=Path("../data"), help="the data/ directory to write")
    r.add_argument("--skip-fetch", action="store_true", help="build from the snapshots already on disk")
    r.add_argument("--only", help="comma-separated source keys to fetch; the others use their newest snapshot")
    r.add_argument("--slugs", type=Path, default=None,
                   help="the slug registry the last build published (default: slugs.json inside --out)")
    r.add_argument("--labels", type=Path, default=None,
                   help="the labelled set of paper names that guesses.json is measured on")
    r.add_argument("--first-build", action="store_true",
                   help="allow a build that starts the slug registry from nothing; every other build needs "
                        "the registry the last one published")
    lk = sub.add_parser("links", help="check a rotating sample of the published report links")
    lk.add_argument("--sample", type=int, default=LINK_SAMPLE, help="most URLs to check this run")
    lk.add_argument("--per-host", type=int, default=LINKS_PER_HOST, help="most URLs to check on any one host")
    lk.add_argument("--workers", type=int, default=LINK_WORKERS, help="hosts checked side by side")
    lk.add_argument("--minutes", type=float, default=LINK_MINUTES, help="stop starting new checks after this long")
    lk.add_argument("--data", type=Path, default=Path("../data"), help="the data/ directory whose reports to check")
    st = sub.add_parser("state", help="pack or restore the snapshots that cannot be fetched again")
    st.add_argument("action", choices=["pack", "unpack"])
    st.add_argument("archive", type=Path, help="the .tar.gz to write (pack) or read (unpack)")
    return p


def feed_sources() -> list[str]:
    """The sources whose snapshots keep posts the publisher no longer serves."""
    return [c.name for c in default_connectors() if isinstance(c, FeedConnector)]


def main(argv: Sequence[str] | None = None, *, store: SnapshotStore | None = None,
         connectors: Sequence[Connector] | None = None) -> int:
    """Exit code 0 when the work was done, 1 when the data contract refused the build."""
    parser = _parser()
    args = parser.parse_args(argv)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stderr)
        # httpx logs one line per request, which drowns the build's own messages.
        logging.getLogger("httpx").setLevel(logging.WARNING)
    store = store or SnapshotStore()

    if args.command == "state":
        feeds = feed_sources()
        if args.action == "pack":
            names = saved_state.pack(store, args.archive, feeds)
        elif not args.archive.is_file():
            print(f"{args.archive} does not exist", file=sys.stderr)
            return 1
        else:
            names = saved_state.unpack(store, args.archive, feeds)
        print(f"{args.action}ed {len(names)} files: {', '.join(names)}")
        return 0

    if args.command == "links":
        if not (args.data / "reports").is_dir():
            print(f"no reports under {args.data}; run `python -m aptx run` first", file=sys.stderr)
            return 1
        checked = check_links(store, report_urls(args.data), args.sample, per_host=args.per_host,
                              workers=args.workers, minutes=args.minutes)
        print(f"checked {len(checked)} links, {sum(1 for r in checked.values() if not r['ok'])} not ok")
        return 0

    only = None
    if args.only:
        only = {k.strip() for k in args.only.split(",") if k.strip()}
        unknown = only - set(SOURCE_ORDER)
        if unknown:
            parser.error(f"unknown source(s) {', '.join(sorted(unknown))}; choose from {', '.join(SOURCE_ORDER)}")
    # A missing registry is only right for the very first build. Anywhere else it means the file
    # was deleted or not copied, and a quiet fresh start would give every actor a new slug and
    # break the addresses that were already published.
    registry_path = args.slugs if args.slugs is not None else args.out / "slugs.json"
    if not args.first_build and not registry_path.is_file():
        print(f"{registry_path} does not exist. Pass the registry the last build published with --slugs, "
              "or pass --first-build if this is the first build.", file=sys.stderr)
        return 1
    try:
        status = run(args.out, store, connectors, fetch=not args.skip_fetch, only=only,
                     slugs_path=args.slugs, labels=args.labels)
    except WriteRefused as e:
        print(e, file=sys.stderr)
        return 1
    except ValueError as e:
        # assemble() refuses inputs it cannot publish safely, such as a missing copyright year or
        # publish policy. That is the same outcome as a schema failure: nothing was written.
        log.exception("build refused: %s", e)
        return 1
    print(f"{'source':<10} {'publish':<14} {'records':>8}  {'last success':<12} state")
    for key in SOURCE_ORDER:
        s = status[key]
        state = "STALE" if s["stale"] else "ok"
        note = f"  ({s['error']})" if s["error"] else ""
        print(f"{key:<10} {s['publish']:<14} {s['record_count']:>8}  {s['last_success'] or '-':<12} {state}{note}")
    return 0
