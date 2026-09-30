import random
import re

import pytest
from jsonschema import Draft202012Validator

from aptx.build.contract import load_schema
from aptx.core.models import ActorRecord, SoftwareRecord
from aptx.resolve.registry import resolve
from aptx.sources import base


def A(src, sid, name, *aliases):
    return ActorRecord(source=src, source_id=sid, name=name, aliases=list(aliases), retrieved_at="2026-09-29")


def S(src, sid, name, kind, *aliases):
    return SoftwareRecord(source=src, source_id=sid, name=name, aliases=list(aliases), kind=kind,
                          retrieved_at="2026-09-29")


def contract_errors(definition: str, value) -> list[str]:
    """Errors from validating value against one $defs entry of resolution.schema.json.

    The registry's output lands in data/resolution.json and in actor file
    names, so it is checked against the published contract itself rather than
    a copy of its patterns.
    """
    defs = load_schema("resolution")["$defs"]
    validator = Draft202012Validator({"$defs": defs, "$ref": f"#/$defs/{definition}"})
    return [e.message for e in validator.iter_errors(value)]


# The plan's three cases.

def test_aliases_merge_across_sources_with_evidence():
    r = resolve([A("attack", "G0007", "APT28", "Fancy Bear", "Sofacy"),
                 A("misp", "u1", "Sofacy", "Sednit", "Pawn Storm"),
                 A("malpedia", "apt28", "APT28", "Sednit")], [])
    assert len(r.actors) == 1
    a = r.actors[0]
    assert a.id == "G0007"
    assert r.lookup("Pawn Storm") == r.lookup("fancy bear") == "G0007"
    assert any(e[0] == "sofacy" for e in a.evidence)


def test_alias_shared_by_two_attack_groups_is_ambiguous_not_merged():
    r = resolve([A("attack", "G0096", "APT41", "Winnti"), A("attack", "G0044", "Winnti Group", "Winnti")], [])
    assert len(r.actors) == 2
    assert r.lookup("Winnti") is None
    assert {"alias": "winnti", "candidates": ["G0044", "G0096"]} in r.ambiguities


def test_software_name_is_typed_not_an_actor():
    r = resolve([A("misp", "u2", "APT1")], [SoftwareRecord(source="malpedia", source_id="win.chinachopper",
                                                           name="China Chopper", kind="malware", retrieved_at="x")])
    assert r.lookup("China Chopper") is None
    assert r.non_actor("china chopper") == "malware"


# Evidence.

def test_evidence_is_a_star_on_the_smallest_record_id_per_shared_key():
    r = resolve([A("misp", "b", "Foo Cat"), A("etda", "a", "Foo Cat"), A("malpedia", "c", "Foo Cat")], [])
    assert r.actors[0].evidence == [("foocat", "etda:a", "malpedia:c"), ("foocat", "etda:a", "misp:b")]


def test_every_member_alias_is_a_claim_with_its_provenance():
    a = resolve([A("attack", "G0007", "APT28", "Fancy Bear"),
                 A("misp", "u1", "Sofacy", "  Fancy   Bear ", "Fancy Bear", " ", "APT28")], []).actors[0]
    claims = [(c.value, c.prov.source, c.prov.source_id) for c in a.aliases]
    assert sorted(claims) == sorted([
        ("APT28", "attack", "G0007"), ("Fancy Bear", "attack", "G0007"),
        ("Sofacy", "misp", "u1"), ("Fancy Bear", "misp", "u1"), ("APT28", "misp", "u1"),
    ])
    assert {c.prov.retrieved_at for c in a.aliases} == {"2026-09-29"}


def test_aliases_with_no_letters_never_link_records():
    r = resolve([A("misp", "m1", "Alpha Cat", "---"), A("misp", "m2", "Beta Cat", "???"),
                 A("etda", "e1", "Gamma Cat", "")], [])
    assert len(r.actors) == 3
    assert r.stats()["evidence_edge_count"] == 0


# Merges that would join two ATT&CK groups.

def test_a_record_bridging_two_attack_groups_never_joins_them():
    r = resolve([A("attack", "G0001", "Alpha", "Shared One"),
                 A("misp", "m1", "Bridge", "Shared One", "Shared Two"),
                 A("attack", "G0002", "Beta", "Shared Two")], [])
    assert r.lookup("Alpha") == "G0001" and r.lookup("Beta") == "G0002"
    for a in r.actors:
        assert len({m.source_id for m in a.members if m.source == "attack"}) <= 1
    # Both links are equally direct, so the lower key wins and the other one is
    # recorded as ambiguous.
    assert r.lookup("Bridge") == "G0001"
    assert r.ambiguities == [{"alias": "sharedtwo", "candidates": ["G0001", "G0002"]}]
    # Only Beta carries "Shared Two" directly, so the refused key still finds it.
    assert r.lookup("Shared Two") == "G0002"


def test_direct_attack_evidence_wins_over_a_chain_of_other_sources():
    r = resolve([A("attack", "G0007", "Alpha", "Xray"),
                 A("misp", "u1", "Mid One", "Xray", "Yankee"),
                 A("malpedia", "m1", "Mid Two", "Yankee", "Zulu"),
                 A("attack", "G0008", "Beta", "Zulu")], [])
    assert r.lookup("Mid One") == "G0007"
    assert r.lookup("Mid Two") == "G0008"
    assert r.ambiguities == [{"alias": "yankee", "candidates": ["G0007", "G0008"]}]


def test_a_shared_primary_name_outranks_a_shared_alias():
    # ETDA-style lumping: a card for APT41 that also lists an alias ATT&CK
    # gives to Winnti Group. The shared name APT41 decides where it belongs.
    r = resolve([A("attack", "G0096", "APT41", "Wicked Panda"),
                 A("attack", "G0044", "Winnti Group", "Blackfly"),
                 A("etda", "e1", "APT 41", "Wicked Panda", "Blackfly")], [])
    assert r.lookup("APT 41") == "G0096"
    assert r.lookup("Wicked Panda") == "G0096"
    # The merge on "Blackfly" was refused, but Winnti Group is the only
    # ATT&CK group that carries the key itself, so the key resolves to it.
    assert r.lookup("Blackfly") == "G0044"
    assert {"alias": "blackfly", "candidates": ["G0044", "G0096"]} in r.ambiguities


def test_a_shared_primary_name_outranks_a_name_on_one_side_only():
    # An ETDA card named for one group that lists another group's name as an
    # alias. Alphabetically "apt41" would be applied first and pull the card
    # into APT41; the shared primary name must win instead.
    r = resolve([A("attack", "G0096", "APT41"), A("attack", "G0044", "Winnti Group"),
                 A("etda", "e1", "Winnti Group", "APT41")], [])
    winnti = next(a for a in r.actors if a.id == "G0044")
    assert ("etda", "e1") in {(m.source, m.source_id) for m in winnti.members}
    assert r.lookup("Winnti Group") == "G0044"
    assert {"alias": "apt41", "candidates": ["G0044", "G0096"]} in r.ambiguities
    # The merge on "APT41" was refused, but APT41 (G0096) is the only ATT&CK
    # group that carries the key itself, so reports tagged APT41 still land on it.
    assert r.lookup("APT41") == "G0096"


# The candidate rule: an ambiguous key still resolves when exactly one ATT&CK
# group carries it directly, as its own name or alias.

def test_apt41_resolves_to_its_group_although_the_etda_card_lumps_it_with_winnti():
    r = resolve([A("attack", "G0096", "APT41"), A("attack", "G0044", "Winnti Group"),
                 A("etda", "e1", "Winnti Group", "APT41")], [])
    assert r.lookup("APT41") == "G0096"
    assert r.lookup("apt 41") == "G0096"        # Any spelling of the key.
    assert r.lookup("Winnti Group") == "G0044"
    # Resolving the key does not undo the refusal: the ambiguity is still
    # written, and the ETDA card is still not merged into APT41.
    assert r.ambiguities == [{"alias": "apt41", "candidates": ["G0044", "G0096"]}]
    apt41 = next(a for a in r.actors if a.id == "G0096")
    assert ("etda", "e1") not in {(m.source, m.source_id) for m in apt41.members}
    assert len(r.actors) == 2


def test_a_key_carried_directly_by_two_attack_groups_still_resolves_to_nothing():
    r = resolve([A("attack", "G0096", "APT41", "Winnti"), A("attack", "G0044", "Winnti Group", "Winnti"),
                 A("etda", "e1", "Winnti Group", "APT41")], [])
    assert r.lookup("Winnti") is None
    assert {"alias": "winnti", "candidates": ["G0044", "G0096"]} in r.ambiguities
    # APT41 is carried by only one group, so it resolves in the same registry.
    assert r.lookup("APT41") == "G0096"


def test_non_attack_records_sharing_only_an_ambiguous_key_stay_unmerged():
    r = resolve([A("attack", "G0096", "APT41"), A("attack", "G0044", "Winnti Group"),
                 A("etda", "e1", "Winnti Group", "APT41"),
                 A("misp", "m1", "Karma One", "APT41"), A("malpedia", "m2", "Karma Two", "APT41")], [])
    homes = {(m.source, m.source_id): a.id for a in r.actors for m in a.members}
    assert homes[("etda", "e1")] == "G0044"
    # Neither newcomer joins a group, and they do not join each other. The key
    # names a real group, but nothing says which one these sources meant.
    assert homes[("misp", "m1")] not in {"G0096", "G0044"}
    assert homes[("malpedia", "m2")] not in {"G0096", "G0044"}
    assert homes[("misp", "m1")] != homes[("malpedia", "m2")]
    # Reports tagged APT41 still resolve to the ATT&CK group.
    assert r.lookup("APT41") == "G0096"
    assert [x["alias"] for x in r.ambiguities] == ["apt41"]


def test_a_key_with_no_attack_carrier_stays_unresolved_even_when_ambiguous():
    # Yankee is only an alias of two non-ATT&CK records that sit under two
    # groups, so there is no group to prefer.
    r = resolve([A("attack", "G0007", "Alpha", "Xray"),
                 A("misp", "u1", "Mid One", "Xray", "Yankee"),
                 A("malpedia", "m1", "Mid Two", "Yankee", "Zulu"),
                 A("attack", "G0008", "Beta", "Zulu")], [])
    assert r.lookup("Yankee") is None
    assert r.ambiguities == [{"alias": "yankee", "candidates": ["G0007", "G0008"]}]


def test_the_candidate_rule_leaves_apt28_and_apt2_apart():
    r = resolve([A("attack", "G0007", "APT28", "Sofacy"), A("attack", "G0087", "APT2"),
                 A("misp", "u1", "APT 28"), A("misp", "u2", "APT-2")], [])
    assert r.lookup("APT28") == "G0007" and r.lookup("APT 28") == "G0007"
    assert r.lookup("APT2") == "G0087" and r.lookup("apt-2") == "G0087"
    assert r.ambiguities == []


def test_stats_stay_exact_when_a_refused_key_still_resolves():
    r = resolve([A("attack", "G0096", "APT41"), A("attack", "G0044", "Winnti Group"),
                 A("etda", "e1", "Winnti Group", "APT41")], [])
    assert r.stats() == {
        "source_record_count": 3, "actor_count": 2, "merge_count": 1,
        "evidence_edge_count": 1, "ambiguity_count": 1, "non_actor_name_count": 0,
    }
    for ambiguity in r.ambiguities:
        assert contract_errors("ambiguity", ambiguity) == []


def test_records_of_one_attack_group_always_share_one_actor():
    r = resolve([A("attack", "G0007", "APT28"), A("attack", "G0007", "Fancy Bear")], [])
    assert [a.id for a in r.actors] == ["G0007"]
    assert r.actors[0].name == "APT28"


# Evidence from sources that are not published.

def test_unpublished_sources_still_count_as_merge_evidence(monkeypatch):
    # What reaches data/ is decided at assembly. The registry must use every
    # record as evidence and never consult the licence gate itself.
    def gate(*args, **kwargs):
        raise AssertionError("the registry must not call publish_policy")
    monkeypatch.setattr(base, "publish_policy", gate)

    r = resolve([A("misp", "m1", "Glass Heron"), A("etda", "e1", "Glass Heron", "Heron Cluster 7"),
                 A("orkl", "o1", "Heron Cluster 7"), A("malpedia", "p1", "GlassHeron"),
                 A("etda", "e9", "Solo Cat")], [])
    heron = r.actors[[a.name for a in r.actors].index("Glass Heron")]
    assert {m.source for m in heron.members} == {"misp", "etda", "orkl", "malpedia"}
    assert r.lookup("Heron Cluster 7") == heron.id
    assert r.lookup("Solo Cat") is not None
    assert r.stats()["actor_count"] == 2
    assert r.stats()["merge_count"] == 3


# Names and IDs.

def test_display_name_is_attack_s_else_the_most_common_name():
    r = resolve([A("misp", "u1", "Sofacy"), A("malpedia", "p1", "Sofacy"), A("attack", "G0007", "APT28", "Sofacy"),
                 A("misp", "m1", "Glass Heron", "Heron7"), A("malpedia", "p2", "Heron7", "Glass Heron"),
                 A("etda", "e1", "Glass Heron")], [])
    names = {a.id: a.name for a in r.actors}
    assert names["G0007"] == "APT28"
    assert names[r.lookup("Heron7")] == "Glass Heron"


def test_actor_ids_are_readable_ascii_slugs():
    r = resolve([A("misp", "m1", "Glass Heron"), A("malpedia", "p1", "Glass Heron"), A("misp", "m2", "Café Bear"),
                 A("misp", "m3", "Лазарь", "Lazar Kitten")], [])
    assert r.lookup("Glass Heron") == "glass-heron"
    assert r.lookup("Café Bear") == "cafe-bear"
    # A name with no ASCII form gets a stable fallback from the record's identity. It must not borrow
    # the alias "Lazar Kitten", because the page never shows that name and a slug must not leak it.
    fallback = r.lookup("Лазарь")
    assert re.fullmatch(r"actor-[0-9a-f]{10}", fallback)
    assert "lazar" not in fallback


@pytest.mark.parametrize("name", ["Index", "INDEX", "Ｉｎｄｅｘ", "海莲花", "G0007", "g1017", "???", "x" * 300])
def test_actor_ids_always_fit_the_contract(name):
    r = resolve([A("misp", "m1", name), A("attack", "G0007", "APT28")], [])
    ids = [a.id for a in r.actors]
    assert len(ids) == len(set(ids)) == 2
    for actor_id in ids:
        assert contract_errors("actorId", actor_id) == [], actor_id
        assert actor_id.casefold() != "index"
        assert len(actor_id) <= 64
    slug_id = next(i for i in ids if i != "G0007")
    # G0007.json and g0007.json are the same file on Windows and macOS.
    assert not re.fullmatch(r"g\d{4}", slug_id, re.IGNORECASE)


def test_colliding_slugs_get_distinct_ids_in_a_fixed_order():
    records = [A("misp", "m2", "Muller Cat"), A("misp", "m1", "Müller Cat"), A("misp", "m0", "Muller Cat 2")]
    for recs in (records, records[::-1]):
        r = resolve(recs, [])
        assert r.lookup("Müller Cat") == "muller-cat"
        assert r.lookup("Muller Cat 2") == "muller-cat-2"
        assert r.lookup("Muller Cat") == "muller-cat-3"


def test_long_slugs_that_collide_after_the_cut_are_numbered_within_the_limit():
    long_one, long_two = "a" * 70 + " one", "a" * 70 + " two"
    # The cut falls just after a word, which would leave a trailing hyphen.
    hyphen_at_cut = "b" * 63 + " c"
    r = resolve([A("misp", "m1", long_one), A("misp", "m2", long_two), A("misp", "m3", hyphen_at_cut)], [])
    assert r.lookup(long_one) == "a" * 64
    assert r.lookup(long_two) == "a" * 62 + "-2"
    assert r.lookup(hyphen_at_cut) == "b" * 63
    for actor in r.actors:
        assert len(actor.id) <= 64
        assert contract_errors("actorId", actor.id) == [], actor.id


def test_an_attack_record_without_a_group_id_gets_a_slug():
    r = resolve([A("attack", "intrusion-set--1234", "Odd Group Record")], [])
    assert r.actors[0].id == "odd-group-record"
    assert contract_errors("actorId", r.actors[0].id) == []


# lookup().

def test_lookup_uses_the_same_key_as_norm():
    r = resolve([A("attack", "G0007", "APT28", "Sofacy"), A("attack", "G0032", "Lazarus Group")], [])
    assert r.lookup("Ｓｏｆａｃｙ") == r.lookup("sofacy group") == r.lookup("APT 28") == "G0007"
    assert r.lookup("LAZARUS") == r.lookup("Ｌａｚａｒｕｓ　Ｇｒｏｕｐ") == "G0032"
    assert r.lookup("APT2") is None
    assert r.lookup("") is None and r.lookup("---") is None and r.lookup("Nobody") is None


# Entity typing.

def test_a_name_any_actor_record_carries_is_never_typed_as_software():
    r = resolve([A("attack", "G0096", "APT41", "Winnti"), A("attack", "G0044", "Winnti Group")],
                [S("malpedia", "win.winnti", "Winnti", "malware")])
    assert r.lookup("Winnti") is None
    assert r.non_actor("Winnti") is None


def test_software_aliases_are_typed_too():
    r = resolve([], [S("malpedia", "win.plugx", "PlugX", "malware", "Korplug")])
    assert r.non_actor("KORPLUG") == "malware"
    assert r.non_actor("") is None and r.non_actor("Unknown Thing") is None


def test_attack_s_software_type_wins_when_sources_disagree():
    software = [S("malpedia", "win.mimikatz", "Mimikatz", "malware"), S("attack", "S0002", "Mimikatz", "tool"),
                S("attack", "S0154", "Cobalt Strike", "malware"), S("other", "x1", "Cobalt Strike", "tool")]
    for sw in (software, software[::-1]):
        r = resolve([], sw)
        assert r.non_actor("mimikatz") == "tool"
        assert r.non_actor("Cobalt Strike") == "malware"


# The published contract.

def test_stats_and_ambiguities_fit_resolution_json():
    r = resolve([A("attack", "G0007", "APT28", "Fancy Bear", "Sofacy"),
                 A("misp", "u1", "Sofacy", "Sednit", "Pawn Storm"),
                 A("malpedia", "apt28", "APT28", "Sednit"),
                 A("attack", "G0096", "APT41", "Winnti"),
                 A("attack", "G0044", "Winnti Group", "Winnti"),
                 A("misp", "u9", "Glass Heron")],
                [S("malpedia", "win.chinachopper", "China Chopper", "malware"),
                 S("attack", "S0002", "Mimikatz", "tool")])
    stats = r.stats()
    assert stats == {
        "source_record_count": 6,
        "actor_count": 4,
        "merge_count": 2,
        "evidence_edge_count": 3,
        "ambiguity_count": 1,
        "non_actor_name_count": 2,
    }
    assert contract_errors("stats", stats) == []
    for ambiguity in r.ambiguities:
        assert contract_errors("ambiguity", ambiguity) == []
    for actor in r.actors:
        assert contract_errors("actorId", actor.id) == []


def test_merge_count_is_records_minus_actors():
    r = resolve([A("misp", str(i), f"Cat {i % 3}") for i in range(10)], [])
    s = r.stats()
    assert s["merge_count"] == s["source_record_count"] - s["actor_count"] == 10 - 3


# Determinism.

def _snapshot(r, names):
    return (
        [(a.id, a.name, [(m.source, m.source_id, m.name) for m in a.members],
          [(c.value, c.prov.source, c.prov.source_id) for c in a.aliases], a.evidence) for a in r.actors],
        r.ambiguities,
        r.stats(),
        {n: (r.lookup(n), r.non_actor(n)) for n in names},
    )


def test_the_result_does_not_depend_on_input_order():
    actors = [
        A("attack", "G0007", "APT28", "Fancy Bear", "Sofacy"), A("misp", "u1", "Sofacy", "Sednit"),
        A("malpedia", "apt28", "APT 28", "Sednit"), A("etda", "e28", "APT 28", "Strontium"),
        A("attack", "G0096", "APT41", "Winnti", "Wicked Panda"), A("attack", "G0044", "Winnti Group", "Blackfly"),
        A("etda", "e41", "APT 41", "Wicked Panda", "Blackfly"), A("misp", "w1", "Winnti"),
        A("malpedia", "w2", "Winnti"),
        A("attack", "G0001", "Alpha", "Xray"), A("misp", "x1", "Mid One", "Xray", "Yankee"),
        A("malpedia", "x2", "Mid Two", "Yankee", "Zulu"), A("attack", "G0002", "Beta", "Zulu"),
        A("misp", "m1", "Müller Cat"), A("misp", "m2", "Muller Cat"), A("misp", "m3", "Index"),
        A("misp", "g1", "Glass Heron", "Heron7"), A("malpedia", "g2", "Heron7", "Glass Heron"),
    ]
    software = [S("malpedia", "win.mimikatz", "Mimikatz", "malware"), S("attack", "S0002", "Mimikatz", "tool"),
                S("malpedia", "win.winnti", "Winnti", "malware"), S("malpedia", "win.plugx", "PlugX", "malware")]
    names = ["Sofacy", "Strontium", "Winnti", "Blackfly", "APT 41", "Yankee", "Mid One", "Mid Two",
             "Muller Cat", "Müller Cat", "Index", "Heron7", "Mimikatz", "PlugX"]
    expected = _snapshot(resolve(actors, software), names)
    for seed in range(6):
        a, s = actors[:], software[:]
        random.Random(seed).shuffle(a)
        random.Random(seed).shuffle(s)
        assert _snapshot(resolve(a, s), names) == expected
    ids = [x[0] for x in expected[0]]
    assert ids == sorted(ids) and len(ids) == len(set(ids))
