"""The similarity signals: what an unresolved name resembles, and the rules that keep the evaluation honest."""
from aptx.core.models import ActorRecord, ReportRecord, SoftwareRecord
from aptx.resolve import similarity as sim
from aptx.resolve.registry import resolve

NOW = "2026-09-29"


def A(src, sid, name, *aliases):
    return ActorRecord(source=src, source_id=sid, name=name, aliases=list(aliases), retrieved_at=NOW)


def S(src, sid, name, kind, *aliases):
    return SoftwareRecord(source=src, source_id=sid, name=name, aliases=list(aliases), kind=kind, retrieved_at=NOW)


def R(sid, names, cves=(), source="paper"):
    return ReportRecord(source=source, source_id=sid, title="t", date_basis="publisher", actor_names=list(names),
                        cves=list(cves), retrieved_at=NOW)


def make(actors=(), software=(), reports=(), **kw):
    registry = resolve(list(actors), list(software))
    return registry, sim.build_reference(registry, list(software), list(reports), **kw)


# Edit distance and name variants

def test_edit_distance_counts_a_swap_of_neighbours_as_one_edit():
    assert sim.edit_distance("hafnuim", "hafnium") == 1
    assert sim.edit_distance("kimsuki", "kimsuky") == 1
    assert sim.edit_distance("same", "same") == 0


def test_edit_distance_gives_up_past_the_cap():
    assert sim.edit_distance("abcdef", "uvwxyz", cap=2) == 3
    assert sim.edit_distance("a", "abcdefgh", cap=2) == 3


def keys(name):
    return {v.key: v.how for v in sim.variants(name)}


def test_a_leading_apt_is_dropped_only_as_a_proposal():
    found = keys("apt sidewinder")
    assert "sidewinder" in found and "leading 'apt'" in found["sidewinder"]


def test_a_plural_and_generic_words_are_dropped_as_variants():
    assert "keyboy" in keys("Keyboys")
    assert "emotet" in keys("emotet gang")
    assert "romcom" in keys("romcom threat actor")


def test_a_bracketed_alias_becomes_its_own_variant():
    assert "sphinx" in keys("Sphinx (APT-C-15)")
    assert "aptc15" in keys("Sphinx (APT-C-15)")


def test_a_variant_that_only_restores_a_trailing_group_word_says_so():
    # names.norm strips the trailing word from the key, so a variant that keeps it must explain itself.
    assert "trailing" in keys("Winnti Group")["winntigroup"]


def test_the_name_itself_is_never_its_own_variant():
    assert sim.norm("Sofacy") not in keys("Sofacy")


# Signals read from the text of the name

def features(name, ref=None, **kw):
    ref = ref or make()[1]
    return sim.analyse(name, ref, **kw).features


def test_cluster_id_patterns_fire_and_ordinary_names_do_not():
    for name in ("UNC1234", "APT-C-15", "TAG-22", "Storm-0558", "FIN7", "DEV-0537", "TA505"):
        assert features(name)["cluster_id"] == 1.0, name
    for name in ("Sofacy", "Lazarus Group", "apt sidewinder"):
        assert features(name)["cluster_id"] == 0.0, name


def test_vendor_suffix_and_malware_word():
    assert features("LOTUS PANDA")["vendor_suffix"] == 1.0
    assert features("Water Kelpie")["vendor_suffix"] == 1.0
    assert features("Sofacy")["vendor_suffix"] == 0.0
    assert features("cosmic banker")["malware_word"] == 1.0
    assert features("Lazarus")["malware_word"] == 0.0


def test_a_script_other_than_latin_is_reported():
    assert features("이름 그룹")["non_latin"] == 1.0
    assert features("Lazarus")["non_latin"] == 0.0


def test_campaign_and_placeholder_names():
    assert sim.is_campaign_name("Operation Falcon")
    assert sim.is_campaign_name("Tibet campaign")
    assert not sim.is_campaign_name("Operational Group")
    assert sim.is_placeholder("Unclassified")
    assert not sim.is_placeholder("unclassified group tag")


# Signals read against the reference

def test_a_spelling_variant_of_an_actor_name_is_a_variant_hit():
    _, ref = make([A("attack", "G0121", "Sidewinder", "Rattlesnake")])
    hit = sim.analyse("apt sidewinder", ref).actor_hit
    assert hit and hit.kind == "variant" and hit.target == "G0121" and hit.target_name == "Sidewinder"
    assert "Sidewinder" in sim.analyse("apt sidewinder", ref).evidence["actor_resemblance"].detail


def test_a_near_spelling_is_a_fuzzy_hit_and_a_different_digit_is_not():
    _, ref = make([A("attack", "G0001", "Kimsuky"), A("attack", "G0002", "APT-C-15")])
    hit = sim.analyse("Kimsuki", ref).actor_hit
    assert hit and hit.kind == "fuzzy" and hit.target_name == "Kimsuky"
    # APT-C-17 is one edit from APT-C-15 and is a different group, as names.norm keeps digits.
    assert sim.analyse("APT-C-17", ref).actor_hit is None


def test_a_name_that_contains_a_known_actor_name_is_a_contains_hit():
    _, ref = make([A("attack", "G0044", "Winnti Group")])
    hit = sim.analyse("Winnti Umbrella", ref).actor_hit
    assert hit and hit.kind == "contains" and hit.target == "G0044"
    assert "'Winnti'" in sim.analyse("Winnti Umbrella", ref).evidence["actor_resemblance"].detail


def test_a_short_shared_word_is_not_a_contains_hit():
    _, ref = make([A("attack", "G0001", "Dark")])
    assert sim.analyse("Dark Halo", ref).actor_hit is None


def test_software_resemblance_names_the_kind_and_the_sources():
    _, ref = make(software=[S("malpedia", "win.emotet", "Emotet", "malware"), S("attack", "S0367", "Emotet", "malware")])
    a = sim.analyse("emotet gang", ref)
    assert a.software_hit.target == "malware"
    assert "ATT&CK and Malpedia" in a.evidence["software_resemblance"].detail


def test_leaving_a_name_out_stops_it_matching_itself():
    _, ref = make([A("attack", "G0001", "Sofacy", "Fancy Bear")])
    assert sim.analyse("Fancy Bear", ref).exact_actor
    left_out = sim.analyse("Fancy Bear", ref, exclude_key=sim.norm("Fancy Bear"))
    assert not left_out.exact_actor and left_out.actor_hit is None


def test_leaving_a_name_out_does_not_hide_other_names_of_the_same_actor():
    _, ref = make([A("attack", "G0001", "Sofacy", "Fancy Bear")])
    hit = sim.analyse("apt sofacy", ref, exclude_key=sim.norm("Fancy Bear")).actor_hit
    assert hit and hit.target == "G0001"


def test_a_known_name_is_never_its_own_co_occurring_actor():
    # In a report row "Fancy Bear" resolves to Sofacy; it must not count as evidence for itself.
    _, ref = make([A("attack", "G0001", "Sofacy", "Fancy Bear")], reports=[R("r1", ["Fancy Bear", "Foo"])])
    left_out = sim.analyse("Fancy Bear", ref, exclude_key=sim.norm("Fancy Bear"))
    assert left_out.features["cooc_actor"] == 0.0 and left_out.related_actor is None


def test_a_report_row_naming_a_known_actor_is_co_occurrence():
    _, ref = make([A("attack", "G0001", "Sofacy")], reports=[R("r1", ["Foo", "Sofacy"])])
    a = sim.analyse("Foo", ref)
    assert a.features["cooc_actor"] == 1.0 and a.related_actor == "G0001"
    assert "Sofacy" in a.evidence["cooc_actor"].detail


def test_a_cve_tied_to_a_few_actors_is_evidence_and_a_common_one_is_not():
    actors = [A("attack", f"G000{i}", f"Actor {i}") for i in range(1, 6)]
    rows = [R("r0", ["Foo"], ["CVE-2020-0001", "CVE-2020-0002"])]
    rows += [R(f"r{i}", [f"Actor {i}"], ["CVE-2020-0001"]) for i in range(1, 2)]
    rows += [R(f"c{i}", [f"Actor {i}"], ["CVE-2020-0002"]) for i in range(1, 6)]
    _, ref = make(actors, reports=rows)
    a = sim.analyse("Foo", ref)
    assert a.features["cve_actor"] == 1.0
    assert "CVE-2020-0001" in a.evidence["cve_actor"].detail and "CVE-2020-0002" not in a.evidence["cve_actor"].detail


def test_only_paper_reports_make_rows_and_orkl_never_does():
    reg = resolve([A("attack", "G0001", "Sofacy")], [])
    ref = sim.build_reference(reg, [], [R("o1", ["Foo", "Sofacy"], source="orkl")])
    assert ref.rows == []


# What the reference may contain

def test_names_from_a_source_that_may_not_be_shown_are_left_out():
    reg = resolve([A("attack", "G0001", "Sofacy", "Fancy Bear"), A("etda", "e1", "Sofacy", "Zebrocy")], [])
    ref = sim.build_reference(reg, [], [], shown_sources={"attack"})
    assert {e.spelling for e in ref.actor_names} == {"Sofacy", "Fancy Bear"}
    assert sim.analyse("Zebrocy", ref).actor_hit is None


def test_software_from_a_source_that_may_not_be_shown_is_left_out():
    reg = resolve([], [S("malpedia", "m1", "Emotet", "malware")])
    ref = sim.build_reference(reg, [S("malpedia", "m1", "Emotet", "malware")], [], shown_sources={"attack"})
    assert ref.software_names == []


def test_only_actors_drops_the_rest_and_uses_the_published_names():
    reg, ref = make([A("attack", "G0001", "Sofacy", "Fancy Bear"), A("attack", "G0002", "Turla")],
                    reports=[R("r1", ["Foo", "Turla"])])
    kept = sim.only_actors(ref, {"G0001": "APT28"})
    assert {e.actor_id for e in kept.actor_names} == {"G0001"}
    assert kept.actor_display == {"G0001": "APT28"}
    assert sim.analyse("Foo", kept).features["cooc_actor"] == 0.0


def test_exact_presence_says_where_a_name_is_listed():
    reg, ref = make([A("attack", "G0001", "Sofacy", "Fancy Bear"), A("misp", "u1", "Sofacy", "Fancy Bear")],
                    [S("malpedia", "m1", "Zebrocy", "malware")])
    [item] = sim.exact_presence("Fancy Bear", ref)
    assert item.signal == "exact_actor_name" and "ATT&CK and MISP" in item.detail
    assert [i.signal for i in sim.exact_presence("Zebrocy", ref)] == ["exact_software_name"]
    assert sim.exact_presence("Nobody", ref) == []


def test_every_signal_has_a_description_and_every_feature_is_a_signal():
    _, ref = make()
    assert set(sim.analyse("anything", ref).features) == set(sim.SIGNALS)
    assert all(text.endswith(".") for text in [*sim.SIGNALS.values(), *sim.RULES.values()])
