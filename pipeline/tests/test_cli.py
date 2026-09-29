import json
from pathlib import Path

import httpx
import pytest
import respx

from aptx import cli
from aptx.build.notice import SOURCE_ORDER
from aptx.build.write import WriteRefused
from aptx.core import http
from aptx.core.models import ActorRecord, ReportRecord, SourceBundle, VulnRecord
from aptx.core.snapshot import ShrunkSnapshotError, SnapshotStore
from aptx.sources.base import Connector
from aptx.sources.orkl import OrklConnector

FIX = Path(__file__).parent / "fixtures"
SNAP = "2026-09-28"
NOW = "2026-09-30T04:00:00Z"
REPORT_URL = "https://example.test/apt28-report"
LICENCE = "\"© 2026 The MITRE Corporation. This work is reproduced and distributed with the permission of The MITRE Corporation.\"\n"


class Fake(Connector):
    """A connector that returns a fixed bundle and can be told to fail its fetch."""

    def __init__(self, name, bundle=None, fail=None, policy="full"):
        self.name, self.bundle, self.fail, self._policy = name, bundle, fail, policy
        self.fetches = 0
        self.policy_calls = 0

    def fetch(self, store):
        self.fetches += 1
        if self.fail:
            raise self.fail

    def normalize(self, store):
        return self.bundle or SourceBundle(source=self.name)

    def policy(self, store, sources_md=None):
        self.policy_calls += 1
        return self._policy


class FakeOrkl(OrklConnector):
    """The real ORKL class with its I/O replaced, so the test sees what the CLI passes to normalize()."""

    def __init__(self, policy="link-only"):
        self.seen = None
        self._policy = policy

    def fetch(self, store):
        pass

    def policy(self, store, sources_md=None):
        return self._policy

    def normalize(self, store, valid_techniques=frozenset(), lib_dates=None):
        self.seen = {"valid_techniques": valid_techniques, "lib_dates": lib_dates}
        return SourceBundle(source="orkl")


def bundles():
    return {
        "attack": SourceBundle(source="attack", actors=[
            ActorRecord(source="attack", source_id="G0007", name="APT28", aliases=["Fancy Bear"], retrieved_at=SNAP)]),
        "misp": SourceBundle(source="misp", actors=[
            ActorRecord(source="misp", source_id="u1", name="Sofacy", aliases=["Fancy Bear"], retrieved_at=SNAP)]),
        "kev": SourceBundle(source="kev", vulns=[
            VulnRecord(cve="CVE-2024-0001", kev_date_added="2024-05-01", ransomware=False, retrieved_at=SNAP)]),
        "dfir": SourceBundle(source="dfir", reports=[
            ReportRecord(source="dfir", source_id="2024-05-01-x", title="A report", published="2024-05-01",
                         date_basis="publisher", url=REPORT_URL, retrieved_at=SNAP)]),
    }


def connectors(**overrides):
    made = bundles()
    out = {key: Fake(key, made.get(key)) for key in SOURCE_ORDER}
    out.update(overrides)
    return [out[key] for key in SOURCE_ORDER]


@pytest.fixture
def store(tmp_path):
    s = SnapshotStore(tmp_path / "cache")
    s.save("attack", "enterprise-attack.json", (FIX / "attack_min.json").read_bytes())
    s.save("attack", "LICENSE.txt", LICENCE.encode("utf-8"))
    for key in SOURCE_ORDER:
        if key != "attack":
            s.save(key, "marker", b"x")
    return s


@pytest.fixture(autouse=True)
def fast_http(monkeypatch):
    # test_http sets these globally and never restores them, so this file sets them itself.
    monkeypatch.setattr(http, "MIN_INTERVAL", 0)
    monkeypatch.setattr(http, "BACKOFF_BASE", 0)


def tree(path: Path) -> dict[str, bytes]:
    return {str(p.relative_to(path)): p.read_bytes() for p in sorted(path.rglob("*")) if p.is_file()}


# run(): stale handling

def test_a_build_publishes_every_source(tmp_path, store):
    out = tmp_path / "data"
    status = cli.run(out, store, connectors(), generated_at=NOW)
    assert set(status) == set(SOURCE_ORDER)
    assert not any(s["stale"] for s in status.values())
    assert (out / "NOTICE.md").exists() and (out / "reports" / "2024.json").exists()
    assert json.loads((out / "vulns.json").read_text(encoding="utf-8"))[0]["cve"] == "CVE-2024-0001"
    # Both actors carry the alias Fancy Bear, so the two records are one actor.
    assert [a["id"] for a in json.loads((out / "actors" / "index.json").read_text(encoding="utf-8"))] == ["G0007"]


@pytest.mark.parametrize("failure", [RuntimeError("boom"), ShrunkSnapshotError("shrank")])
def test_a_failed_fetch_marks_the_source_stale_and_publishes_its_previous_snapshot(tmp_path, store, failure):
    out = tmp_path / "data"
    status = cli.run(out, store, connectors(dfir=Fake("dfir", bundles()["dfir"], fail=failure, policy="link-only")),
                     generated_at=NOW)
    assert status["dfir"]["stale"] is True
    assert type(failure).__name__ in status["dfir"]["error"]
    assert status["dfir"]["record_count"] == 1
    assert [r["id"] for r in json.loads((out / "reports" / "2024.json").read_text(encoding="utf-8"))] == ["dfir:2024-05-01-x"]
    assert status["kev"]["stale"] is False


def test_a_source_with_no_snapshot_at_all_is_stale_and_empty_and_the_build_succeeds(tmp_path, store):
    empty = SnapshotStore(tmp_path / "empty")
    empty.save("attack", "LICENSE.txt", LICENCE.encode("utf-8"))
    status = cli.run(tmp_path / "data", empty, connectors(kev=Fake("kev", fail=RuntimeError("down"))), generated_at=NOW)
    assert status["kev"]["stale"] is True and status["kev"]["record_count"] == 0
    assert (tmp_path / "data" / "sources.json").exists()


def test_skip_fetch_never_fetches_and_only_limits_which_sources_are_fetched(tmp_path, store):
    cs = connectors()
    cli.run(tmp_path / "a", store, cs, fetch=False, generated_at=NOW)
    assert [c.fetches for c in cs] == [0] * 8
    cli.run(tmp_path / "b", store, cs, only={"misp", "kev"}, generated_at=NOW)
    assert {c.name: c.fetches for c in cs if c.fetches} == {"misp": 1, "kev": 1}


def test_a_rebuild_with_skip_fetch_still_reports_the_source_that_failed_to_fetch(tmp_path, store):
    # The weekly workflow rebuilds from snapshots after the link check, and that build must not
    # publish a source as fresh when its fetch failed earlier in the same workflow.
    failing = connectors(dfir=Fake("dfir", bundles()["dfir"], fail=RuntimeError("down"), policy="link-only"))
    cli.run(tmp_path / "first", store, failing, generated_at=NOW)
    status = cli.run(tmp_path / "second", store, failing, fetch=False, generated_at=NOW)
    assert status["dfir"]["stale"] is True
    # A later successful fetch clears it.
    status = cli.run(tmp_path / "third", store, connectors(), generated_at=NOW)
    assert status["dfir"]["stale"] is False


def test_a_damaged_fetch_status_file_does_not_stop_a_build(tmp_path, store):
    (store.root / cli.FETCH_STATUS).write_text("{not json", encoding="utf-8")
    assert cli.run(tmp_path / "data", store, connectors(), fetch=False, generated_at=NOW)["kev"]["stale"] is False


def test_each_policy_is_asked_once_per_build(tmp_path, store):
    cs = connectors()
    cli.run(tmp_path / "data", store, cs, generated_at=NOW)
    assert [c.policy_calls for c in cs] == [1] * 8


def test_the_registry_is_built_from_evidence_only_sources_too(tmp_path, store):
    cs = connectors(misp=Fake("misp", bundles()["misp"], policy="evidence-only"))
    out = tmp_path / "data"
    cli.run(out, store, cs, generated_at=NOW)
    resolution = json.loads((out / "resolution.json").read_text(encoding="utf-8"))
    # MISP's record is merged into G0007 although nothing from MISP is published.
    assert resolution["stats"]["source_record_count"] == 2 and resolution["stats"]["actor_count"] == 1


# run(): ORKL wiring

def test_orkl_gets_the_attack_technique_set_and_malpedia_dates_when_malpedia_may_be_shown(tmp_path, store):
    store.save("malpedia", "library.bib", (FIX / "malpedia_min.bib").read_bytes())
    orkl = FakeOrkl()
    cli.run(tmp_path / "data", store, connectors(orkl=orkl, malpedia=Fake("malpedia", policy="derived-only")), generated_at=NOW)
    assert orkl.seen["valid_techniques"] == frozenset({"T1059", "T1059.001", "T1003"})
    assert orkl.seen["lib_dates"]["example.com/a"] == "2021-05-06"


def test_orkl_gets_no_malpedia_dates_when_malpedia_is_evidence_only(tmp_path, store):
    store.save("malpedia", "library.bib", (FIX / "malpedia_min.bib").read_bytes())
    orkl = FakeOrkl()
    cli.run(tmp_path / "data", store, connectors(orkl=orkl, malpedia=Fake("malpedia", policy="evidence-only")), generated_at=NOW)
    assert orkl.seen["lib_dates"] == {}


def test_the_real_orkl_class_is_recognised_by_type_not_by_name(tmp_path, store):
    orkl = FakeOrkl()
    cli.run(tmp_path / "data", store, connectors(orkl=orkl), generated_at=NOW)
    assert orkl.seen is not None


# run(): refusal

def test_a_schema_failure_returns_1_and_leaves_data_untouched(tmp_path, store, monkeypatch, capsys):
    out = tmp_path / "data"
    assert cli.main(["run", "--out", str(out), "--skip-fetch"], store=store, connectors=connectors()) == 0
    before = tree(out)
    # An actor with no name is the failure the plan names.
    real = cli.assembly.assemble

    def broken(*a, **kw):
        payload = real(*a, **kw)
        del payload["actors/G0007.json"]["name"]
        return payload
    monkeypatch.setattr(cli.assembly, "assemble", broken)
    assert cli.main(["run", "--out", str(out), "--skip-fetch"], store=store, connectors=connectors()) == 1
    assert "name" in capsys.readouterr().err
    assert tree(out) == before


def test_run_raises_write_refused_and_writes_nothing(tmp_path, store, monkeypatch):
    monkeypatch.setattr(cli.assembly, "assemble", lambda *a, **kw: {"build.json": {}})
    with pytest.raises(WriteRefused):
        cli.run(tmp_path / "data", store, connectors())
    assert not (tmp_path / "data").exists()


def test_a_missing_copyright_year_returns_1_and_writes_nothing(tmp_path, capsys):
    bare = SnapshotStore(tmp_path / "bare")
    assert cli.main(["run", "--out", str(tmp_path / "data"), "--skip-fetch"], store=bare, connectors=connectors()) == 1
    assert not (tmp_path / "data").exists()


def test_an_unknown_source_in_only_is_a_usage_error(tmp_path, store):
    with pytest.raises(SystemExit) as e:
        cli.main(["run", "--out", str(tmp_path / "d"), "--only", "attack,nope"], store=store, connectors=connectors())
    assert e.value.code == 2


def test_the_status_table_is_printed(tmp_path, store, capsys):
    cs = connectors(dfir=Fake("dfir", bundles()["dfir"], fail=RuntimeError("down"), policy="link-only"))
    assert cli.main(["run", "--out", str(tmp_path / "data")], store=store, connectors=cs) == 0
    text = capsys.readouterr().out
    assert "dfir" in text and "STALE" in text and "RuntimeError: down" in text


def test_the_default_connectors_are_the_eight_sources_in_notice_order():
    assert [c.name for c in cli.default_connectors()] == list(SOURCE_ORDER)


# The link check

def write_reports(data: Path, urls):
    (data / "reports").mkdir(parents=True)
    rows = [{"id": f"r{i}", "url": u} for i, u in enumerate(urls)]
    rows.append({"id": "no-url", "url": None})
    (data / "reports" / "2024.json").write_text(json.dumps(rows), encoding="utf-8")


@respx.mock
def test_a_404_sets_ok_false_and_a_200_sets_ok_true(tmp_path):
    respx.head("https://a.test/gone").mock(return_value=httpx.Response(404))
    respx.head("https://a.test/fine").mock(return_value=httpx.Response(200))
    s = SnapshotStore(tmp_path)
    got = cli.check_links(s, ["https://a.test/gone", "https://a.test/fine"], now=NOW)
    assert got["https://a.test/gone"] == {"ok": False, "status": 404, "checked_at": NOW}
    assert got["https://a.test/fine"] == {"ok": True, "status": 200, "checked_at": NOW}
    assert cli.load_link_status(s) == got


@respx.mock
def test_a_timeout_records_the_exception_name(tmp_path):
    respx.head("https://a.test/slow").mock(side_effect=httpx.ConnectTimeout("too slow"))
    got = cli.check_links(SnapshotStore(tmp_path), ["https://a.test/slow"], now=NOW)
    assert got["https://a.test/slow"] == {"ok": False, "status": "ConnectTimeout", "checked_at": NOW}


@respx.mock
def test_get_is_the_fallback_when_head_is_refused(tmp_path):
    head = respx.head("https://a.test/nohead").mock(return_value=httpx.Response(405))
    get = respx.get("https://a.test/nohead").mock(return_value=httpx.Response(200, text="body"))
    got = cli.check_links(SnapshotStore(tmp_path), ["https://a.test/nohead"], now=NOW)
    assert got["https://a.test/nohead"]["ok"] is True and head.call_count == 1 and get.call_count == 1


@respx.mock
def test_a_server_that_refuses_robots_is_not_called_dead(tmp_path):
    respx.head("https://a.test/walled").mock(return_value=httpx.Response(403))
    respx.get("https://a.test/walled").mock(return_value=httpx.Response(403))
    got = cli.check_links(SnapshotStore(tmp_path), ["https://a.test/walled"], now=NOW)
    assert got["https://a.test/walled"] == {"ok": True, "status": 403, "checked_at": NOW}


@respx.mock
def test_a_server_error_is_recorded_as_not_ok(tmp_path):
    respx.head("https://a.test/err").mock(return_value=httpx.Response(503))
    assert cli.check_links(SnapshotStore(tmp_path), ["https://a.test/err"], now=NOW)["https://a.test/err"]["ok"] is False


@respx.mock
def test_earlier_results_survive_a_new_run(tmp_path):
    respx.head("https://a.test/one").mock(return_value=httpx.Response(404))
    respx.head("https://a.test/two").mock(return_value=httpx.Response(200))
    s = SnapshotStore(tmp_path)
    cli.check_links(s, ["https://a.test/one"], now="2026-09-01T00:00:00Z")
    cli.check_links(s, ["https://a.test/two"], now=NOW)
    stored = cli.load_link_status(s)
    assert stored["https://a.test/one"]["ok"] is False and stored["https://a.test/one"]["checked_at"] == "2026-09-01T00:00:00Z"
    assert stored["https://a.test/two"]["ok"] is True


@respx.mock
def test_the_sample_takes_unchecked_urls_first_then_the_oldest_checked(tmp_path):
    s = SnapshotStore(tmp_path)
    (tmp_path / "links").mkdir()
    (tmp_path / "links" / "status.json").write_text(json.dumps({
        "https://a.test/old": {"ok": True, "status": 200, "checked_at": "2026-01-01T00:00:00Z"},
        "https://a.test/recent": {"ok": True, "status": 200, "checked_at": "2026-09-01T00:00:00Z"}}), encoding="utf-8")
    routes = {name: respx.head(f"https://a.test/{name}").mock(return_value=httpx.Response(200))
              for name in ("old", "recent", "new")}
    got = cli.check_links(s, ["https://a.test/recent", "https://a.test/old", "https://a.test/new"], sample=2, now=NOW)
    assert sorted(got) == ["https://a.test/new", "https://a.test/old"]
    assert routes["recent"].call_count == 0


@respx.mock
def test_the_links_command_reads_urls_from_the_published_reports(tmp_path, store, capsys):
    data = tmp_path / "data"
    write_reports(data, ["https://a.test/x", "https://a.test/x", "https://a.test/y"])
    respx.head("https://a.test/x").mock(return_value=httpx.Response(200))
    respx.head("https://a.test/y").mock(return_value=httpx.Response(404))
    assert cli.main(["links", "--sample", "300", "--data", str(data)], store=store) == 0
    assert "checked 2 links, 1 not ok" in capsys.readouterr().out
    assert set(cli.load_link_status(store)) == {"https://a.test/x", "https://a.test/y"}


def test_the_links_command_needs_a_built_data_directory(tmp_path, store):
    assert cli.main(["links", "--data", str(tmp_path / "missing")], store=store) == 1


def test_a_build_reads_the_link_results_into_url_ok(tmp_path, store):
    (store.root / "links").mkdir()
    (store.root / "links" / "status.json").write_text(json.dumps({
        REPORT_URL: {"ok": False, "status": 404, "checked_at": NOW}}), encoding="utf-8")
    out = tmp_path / "data"
    cli.run(out, store, connectors(), generated_at=NOW)
    [report] = json.loads((out / "reports" / "2024.json").read_text(encoding="utf-8"))
    assert report["url_ok"] is False
