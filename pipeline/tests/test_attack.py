import json
from pathlib import Path

import httpx
import pytest
import respx

from aptx.core import http
from aptx.core.snapshot import ShrunkSnapshotError, SnapshotStore
from aptx.sources import attack
from aptx.sources.attack import AttackConnector
from aptx.sources.base import Connector

FIX = Path(__file__).parent / "fixtures" / "attack_min.json"
ICS = Path(__file__).parent / "fixtures" / "attack_ics_min.json"
MOBILE = Path(__file__).parent / "fixtures" / "attack_mobile_min.json"

# The two lines of attack-stix-data's LICENSE.txt that matter here, in the
# file's own layout: the licence paragraph, then the quoted designation.
LICENCE_TXT = (
    "License\n-------\n"
    "The MITRE Corporation (MITRE) hereby grants you a non-exclusive, royalty-free license to use ATT&CK® for research,\n"
    "development, and commercial purposes. Any copy you make for such purposes is authorized provided that you reproduce\n"
    "MITRE's copyright designation and this license in any such copy.\n\n"
    "\"© 2026 The MITRE Corporation. This work is reproduced and distributed with the permission of The MITRE Corporation.\"\n"
).encode("utf-8")


@pytest.fixture
def store(tmp_path):
    s = SnapshotStore(tmp_path)
    s.save("attack", "enterprise-attack.json", FIX.read_bytes())
    return s


def test_normalizes_groups_campaigns_and_software(tmp_path):
    store = SnapshotStore(tmp_path)
    store.save("attack", "enterprise-attack.json", FIX.read_bytes())
    b = AttackConnector().normalize(store)
    [g] = b.actors
    assert (g.source_id, g.name) == ("G0007", "APT28")
    assert {"Fancy Bear", "Sofacy"} <= set(g.aliases)
    assert g.techniques == ["T1059"] and g.malware == ["JHUHUGIT"]
    [c] = b.campaigns
    assert (c.source_id, c.first_seen, c.last_seen, c.actor_refs) == ("C0001", "2023-01-01", "2024-06-01", ["G0007"])
    assert {s.name for s in b.software} == {"JHUHUGIT", "Mimikatz"}


def test_aliases_leave_out_the_name_and_repeats(store):
    [g] = AttackConnector().normalize(store).actors
    # ATT&CK lists the group's own name first among its aliases. The name is
    # already the record's name, so repeating it as an alias adds nothing.
    assert g.aliases == ["Fancy Bear", "Sofacy"]
    assert g.source == "attack"


def test_revoked_and_deprecated_links_do_not_count(store):
    # The fixture links G0007 to a revoked technique (T1086), through a revoked
    # relationship to Mimikatz and through a deprecated relationship to T1003.
    # ATT&CK no longer asserts any of those, so none of them may appear.
    [g] = AttackConnector().normalize(store).actors
    assert "T1086" not in g.techniques and "T1003" not in g.techniques
    assert "Mimikatz" not in g.malware


def test_campaign_techniques_and_report_urls(store):
    [c] = AttackConnector().normalize(store).campaigns
    assert c.name == "Fixture Campaign"
    assert c.techniques == ["T1059.001"]
    assert c.report_urls == [
        "https://example.org/reports/c0001",
        "https://example.org/reports/c0001-attribution",
        "https://example.org/reports/c0001-powershell",
    ]


def test_software_kinds_ids_and_aliases(store):
    sw = {s.source_id: s for s in AttackConnector().normalize(store).software}
    assert set(sw) == {"S0044", "S0002"}
    assert (sw["S0044"].kind, sw["S0044"].aliases) == ("malware", ["Seduploader", "JKEYSKW"])
    assert (sw["S0002"].kind, sw["S0002"].aliases) == ("tool", [])


def test_object_without_an_attack_id_is_dropped_and_logged(store, caplog):
    with caplog.at_level("WARNING"):
        b = AttackConnector().normalize(store)
    assert "Group Without An ID" not in {a.name for a in b.actors}
    assert "attack: dropped 1" in caplog.text


def test_unmapped_objects_are_ignored_even_without_a_name(store, caplog):
    # The real bundle holds tactics, matrices, mitigations and other objects
    # that carry an ATT&CK ID. None of them becomes a record, so a missing
    # name on one of them must neither crash normalize() nor count as dropped.
    # The fixture's tactic TA0002 has no name.
    with caplog.at_level("WARNING"):
        b = AttackConnector().normalize(store)
    ids = {r.source_id for r in [*b.actors, *b.campaigns, *b.software]}
    assert "TA0002" not in ids
    assert "dropped 1 " in caplog.text


def test_retrieved_at_is_the_snapshot_date_not_today(tmp_path):
    # normalize() may be reading an old snapshot after a failed fetch, and a
    # stale snapshot must not claim to be fresh.
    d = tmp_path / "attack" / "2026-01-02"
    d.mkdir(parents=True)
    (d / "enterprise-attack.json").write_bytes(FIX.read_bytes())
    b = AttackConnector().normalize(SnapshotStore(tmp_path))
    assert {r.retrieved_at for r in [*b.actors, *b.campaigns, *b.software]} == {"2026-01-02"}


def test_no_snapshot_gives_an_empty_bundle(tmp_path, caplog):
    with caplog.at_level("WARNING"):
        b = AttackConnector().normalize(SnapshotStore(tmp_path))
    assert (b.source, b.actors, b.campaigns, b.software) == ("attack", [], [], [])
    assert "attack" in caplog.text


def test_group_reference_urls_collect_group_and_relationship_citations(store):
    # These URLs are what later links ORKL, DFIR and paper reports to an
    # actor. Citations on revoked relationships, or on links to revoked
    # objects, are left out along with the links themselves.
    assert attack.group_reference_urls(store) == {"G0007": [
        "https://example.org/reports/apt28-2016",
        "https://example.org/reports/apt28-2017",
        "https://example.org/reports/c0001-attribution",
    ]}


def test_group_reference_urls_without_a_snapshot(tmp_path):
    assert attack.group_reference_urls(SnapshotStore(tmp_path)) == {}


def test_copyright_year_comes_from_the_licence_file(store):
    store.save("attack", "LICENSE.txt", LICENCE_TXT)
    assert attack.copyright_year(store) == "2026"


def test_copyright_year_is_none_without_a_designation(tmp_path):
    store = SnapshotStore(tmp_path)
    assert attack.copyright_year(store) is None
    store.save("attack", "LICENSE.txt", b"License\n-------\nNo designation here.\n")
    assert attack.copyright_year(store) is None


def test_is_a_connector():
    assert isinstance(AttackConnector(), Connector)
    assert AttackConnector.name == "attack"


@pytest.fixture
def fast_http(monkeypatch):
    monkeypatch.setattr(http, "MIN_INTERVAL", 0)
    monkeypatch.setattr(http, "BACKOFF_BASE", 0)


def _mock_matrices(enterprise=None, ics=None, mobile=None):
    for matrix, fixture in (("enterprise", enterprise or FIX), ("ics", ics or ICS), ("mobile", mobile or MOBILE)):
        payload = fixture if isinstance(fixture, bytes) else fixture.read_bytes()
        respx.get(attack.bundle_url(matrix)).mock(return_value=httpx.Response(200, content=payload))
    respx.get(attack.LICENCE_URL).mock(return_value=httpx.Response(200, content=LICENCE_TXT))


@respx.mock
def test_fetch_saves_every_matrix_and_the_licence(tmp_path, fast_http):
    _mock_matrices()
    store = SnapshotStore(tmp_path)
    AttackConnector().fetch(store)
    assert store.latest("attack", "enterprise-attack.json") == FIX.read_bytes()
    assert store.latest("attack", "ics-attack.json") == ICS.read_bytes()
    assert store.latest("attack", "mobile-attack.json") == MOBILE.read_bytes()
    assert attack.copyright_year(store) == "2026"


@respx.mock
def test_fetch_refuses_a_bundle_with_no_objects(tmp_path, fast_http):
    # On a first run there is no earlier snapshot for the size guard to
    # compare against, so an empty bundle must be refused on its content.
    _mock_matrices(enterprise=json.dumps({"type": "bundle", "objects": []}).encode())
    store = SnapshotStore(tmp_path)
    with pytest.raises(ValueError):
        AttackConnector().fetch(store)
    assert store.latest_date("attack") is None


@respx.mock
def test_fetch_refuses_an_empty_ics_bundle_before_saving_anything(tmp_path, fast_http):
    # Every bundle is checked before any is saved, so a bad Mobile or ICS file
    # cannot leave a half-new snapshot behind a good Enterprise one.
    _mock_matrices(ics=json.dumps({"type": "bundle", "objects": []}).encode())
    store = SnapshotStore(tmp_path)
    with pytest.raises(ValueError):
        AttackConnector().fetch(store)
    assert store.latest_date("attack") is None


@respx.mock
def test_shrunken_bundle_keeps_the_old_snapshot_and_its_date(tmp_path, fast_http):
    old = tmp_path / "attack" / "2026-01-02"
    old.mkdir(parents=True)
    (old / "enterprise-attack.json").write_bytes(FIX.read_bytes() + b" " * 100_000)
    _mock_matrices()
    store = SnapshotStore(tmp_path)
    with pytest.raises(ShrunkSnapshotError):
        AttackConnector().fetch(store)
    # The licence is saved only after the bundle. Had it been saved first, a
    # new dated folder would make the old bundle look fresh.
    assert store.latest_date("attack") == "2026-01-02"
    assert store.latest("attack", "LICENSE.txt") is None


def test_technique_ids_holds_live_techniques_and_sub_techniques_only(store):
    # The fixture has a revoked T1086, which ATT&CK replaced, so it is not a valid ID any more.
    assert attack.technique_ids(store) == frozenset({"T1059", "T1059.001", "T1003"})


def test_technique_ids_is_empty_without_a_snapshot(tmp_path):
    assert attack.technique_ids(SnapshotStore(tmp_path)) == frozenset()


@pytest.fixture
def all_matrices(tmp_path):
    s = SnapshotStore(tmp_path)
    s.save("attack", "enterprise-attack.json", FIX.read_bytes())
    s.save("attack", "ics-attack.json", ICS.read_bytes())
    s.save("attack", "mobile-attack.json", MOBILE.read_bytes())
    return s


def test_ics_and_mobile_add_groups_campaigns_and_software(all_matrices):
    b = AttackConnector().normalize(all_matrices)
    assert {a.source_id for a in b.actors} == {"G0007", "G9001", "G9002"}
    assert {c.source_id for c in b.campaigns} == {"C0001", "C9001"}
    assert {s.source_id for s in b.software} == {"S0044", "S0002", "S9001", "S9002", "S9003"}
    kinds = {s.source_id: s.kind for s in b.software}
    assert (kinds["S9001"], kinds["S9002"], kinds["S9003"]) == ("malware", "malware", "tool")


def test_a_group_in_several_matrices_is_one_record_and_enterprise_wins(all_matrices):
    # APT28 is in all three bundles under one STIX ID. It must not be doubled,
    # its Enterprise aliases must survive, and the ICS technique joins the
    # technique list that Enterprise already gave it.
    apt28 = [a for a in AttackConnector().normalize(all_matrices).actors if a.source_id == "G0007"]
    assert len(apt28) == 1
    assert apt28[0].aliases == ["Fancy Bear", "Sofacy"]
    assert apt28[0].techniques == ["T0801", "T1059"]


def test_matrix_only_groups_keep_their_own_links(all_matrices):
    by_id = {a.source_id: a for a in AttackConnector().normalize(all_matrices).actors}
    assert by_id["G9001"].techniques == ["T0801"] and by_id["G9001"].malware == ["Fixture PLC Worm"]
    assert by_id["G9001"].aliases == ["FICS"]
    assert by_id["G9002"].techniques == ["T1404"] and by_id["G9002"].malware == ["Fixture Phone Implant"]
    [c] = [c for c in AttackConnector().normalize(all_matrices).campaigns if c.source_id == "C9001"]
    assert c.actor_refs == ["G9001"]


def test_technique_ids_include_ics_and_mobile(all_matrices):
    assert attack.technique_ids(all_matrices) == frozenset(
        {"T1059", "T1059.001", "T1003", "T0801", "T1404"})


def test_a_missing_ics_or_mobile_snapshot_leaves_enterprise_alone(tmp_path):
    # A store written before ICS and Mobile were added holds Enterprise only.
    s = SnapshotStore(tmp_path)
    s.save("attack", "enterprise-attack.json", FIX.read_bytes())
    b = AttackConnector().normalize(s)
    assert {a.source_id for a in b.actors} == {"G0007"}


def test_without_enterprise_nothing_is_read_even_if_ics_exists(tmp_path):
    s = SnapshotStore(tmp_path)
    s.save("attack", "ics-attack.json", ICS.read_bytes())
    b = AttackConnector().normalize(s)
    assert (b.actors, b.campaigns, b.software) == ([], [], [])
