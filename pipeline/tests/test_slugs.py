"""Actor slugs come from the displayed name only and never change once published.

The registry (data/slugs.json) is what carries a slug from one build to the
next, so most tests here build twice: once to make a registry, once with that
registry as `previous_slugs` after the sources changed.
"""
import json
import random
import re

import pytest
from jsonschema import Draft202012Validator

from aptx.build import slugs
from aptx.build.contract import load_schema, schema_for
from aptx.core.models import ActorRecord
from aptx.resolve.registry import resolve


def A(src, sid, name, *aliases):
    return ActorRecord(source=src, source_id=sid, name=name, aliases=list(aliases), retrieved_at="2026-09-29")


def build(records, previous=None, day="2026-09-30", shown=None):
    return resolve(records, [], previous_slugs=previous, shown_sources=shown, build_date=day)


def entry(reg, slug):
    return next(e for e in reg.slug_entries if e["slug"] == slug)


def active(reg):
    return {e["slug"] for e in reg.slug_entries if not e["retired"]}


# --- A slug is derived from the displayed name and nothing else -------------

def test_first_build_gives_each_actor_the_slug_of_its_name():
    reg = build([A("misp", "m1", "Glass Heron"), A("misp", "m2", "Café Bear")])
    assert reg.lookup("Glass Heron") == "glass-heron"
    assert reg.lookup("Café Bear") == "cafe-bear"
    e = entry(reg, "glass-heron")
    assert e["display_name"] == "Glass Heron"
    assert e["anchors"] == ["misp:m1"]
    assert e["first_published"] == "2026-09-30"
    assert (e["suffix"], e["retired"], e["merged_into"]) == (None, False, None)


def test_a_hidden_alias_never_reaches_a_slug_or_the_registry():
    # Two evidence-only sources call the actor "Loud Wolf", more often than the one shown
    # source calls it "Quiet Fox". Counting every member would display "Loud Wolf".
    records = [A("misp", "m1", "Quiet Fox"),
               A("etda", "e1", "Loud Wolf", "Loud Wolf Group"),
               A("malpedia", "p1", "Loud Wolf", "Quiet Fox")]
    reg = build(records, shown={"misp"})
    assert [a.id for a in reg.actors] == ["quiet-fox"]
    text = json.dumps(reg.slug_entries).casefold()
    for hidden in ("loud", "wolf", "etda", "malpedia", "e1", "p1"):
        assert hidden not in text
    assert entry(reg, "quiet-fox")["anchors"] == ["misp:m1"]


def test_seeing_every_source_would_have_used_the_hidden_name():
    # The counterpart of the test above: it is the shown set that decides, not the record order.
    records = [A("misp", "m1", "Quiet Fox"), A("etda", "e1", "Loud Wolf", "Quiet Fox"),
               A("malpedia", "p1", "Loud Wolf", "Quiet Fox")]
    assert [a.id for a in build(records).actors] == ["loud-wolf"]


def test_an_actor_with_no_published_member_is_not_in_the_registry():
    reg = build([A("misp", "m1", "Quiet Fox"), A("etda", "e1", "Secret Bear")], shown={"misp"})
    assert active(reg) == {"quiet-fox"}
    assert len(reg.actors) == 2
    hidden = next(a for a in reg.actors if a.id != "quiet-fox")
    assert re.fullmatch(r"hidden-[0-9a-f]{10}", hidden.id)
    assert "secret" not in hidden.id


def test_a_name_with_no_ascii_form_gets_a_stable_fallback_and_never_a_hidden_alias():
    # "Ocean Lotus" is listed by a source that is not shown, so it may not name the page.
    shown_only = [A("misp", "m1", "海莲花")]
    with_hidden = [A("misp", "m1", "海莲花"), A("etda", "e1", "Ocean Lotus", "海莲花")]
    a = build(shown_only, shown={"misp"}).actors[0].id
    b = build(with_hidden, shown={"misp"}).actors[0].id
    assert a == b
    assert re.fullmatch(r"actor-[0-9a-f]{10}", a)
    assert "lotus" not in b


def test_a_visible_alias_does_not_name_the_actor_either():
    # Before this change a visible alias could stand in for a name with no ASCII form. The page
    # shows the display name, so the slug uses that or a hash.
    reg = build([A("misp", "m1", "Лазарь", "Lazar Kitten")])
    assert re.fullmatch(r"actor-[0-9a-f]{10}", reg.actors[0].id)


def test_the_fallback_does_not_change_when_only_a_hidden_member_changes():
    base = [A("misp", "m1", "海莲花")]
    first = build(base + [A("etda", "e1", "One")], shown={"misp"}).actors
    second = build(base + [A("etda", "e2", "Two")], shown={"misp"}).actors
    ids = lambda actors: sorted(a.id for a in actors if a.id.startswith("actor-"))  # noqa: E731
    assert ids(first) == ids(second) and len(ids(first)) == 1


@pytest.mark.parametrize("name", ["index", "Index", "INDEX", "Ｉｎｄｅｘ"])
def test_the_reserved_name_index_is_numbered_and_the_number_is_recorded(name):
    reg = build([A("misp", "m1", name)])
    assert reg.actors[0].id == "index-2"
    e = entry(reg, "index-2")
    assert e["suffix"] == 2
    assert Draft202012Validator(load_schema("slugs")).is_valid(slugs.document(reg.slug_entries))


def test_long_names_are_cut_within_the_limit():
    reg = build([A("misp", "m1", "a" * 70 + " one"), A("misp", "m2", "a" * 70 + " two")])
    assert sorted(a.id for a in reg.actors) == ["a" * 62 + "-2", "a" * 64]
    assert entry(reg, "a" * 62 + "-2")["suffix"] == 2


# --- A slug is frozen -------------------------------------------------------

def test_a_rename_keeps_the_slug():
    first = build([A("misp", "m1", "Glass Heron")])
    second = build([A("misp", "m1", "Crystal Heron")], first.slug_entries, day="2026-10-07")
    assert second.lookup("Crystal Heron") == "glass-heron"
    e = entry(second, "glass-heron")
    assert e["display_name"] == "Crystal Heron"
    # The slug and the date it was first given out are the actor's, whatever it is called now.
    assert e["first_published"] == "2026-09-30"
    assert len(second.slug_entries) == 1


def test_a_source_dropping_a_member_keeps_the_slug_through_the_remaining_ones():
    first = build([A("misp", "m1", "Glass Heron"), A("malpedia", "p1", "Glass Heron")])
    second = build([A("malpedia", "p1", "Glass Heron")], first.slug_entries, day="2026-10-07")
    assert second.actors[0].id == "glass-heron"
    assert entry(second, "glass-heron")["anchors"] == ["malpedia:p1"]


def test_a_merge_keeps_the_oldest_slug_and_retires_the_other():
    old = build([A("misp", "m2", "Beta Wolf")], day="2026-01-01")
    apart = build([A("misp", "m2", "Beta Wolf"), A("misp", "m1", "Alpha Bear")], old.slug_entries, day="2026-02-01")
    assert active(apart) == {"alpha-bear", "beta-wolf"}
    merged = build([A("misp", "m2", "Beta Wolf", "Alpha Bear"), A("misp", "m1", "Alpha Bear")],
                   apart.slug_entries, day="2026-03-01")
    assert [a.id for a in merged.actors] == ["beta-wolf"]
    assert active(merged) == {"beta-wolf"}
    gone = entry(merged, "alpha-bear")
    assert (gone["retired"], gone["merged_into"]) == (True, "beta-wolf")
    assert gone["first_published"] == "2026-02-01"
    assert entry(merged, "beta-wolf")["anchors"] == ["misp:m1", "misp:m2"]
    # Every name of the merged actor resolves to the surviving slug.
    assert merged.lookup("Alpha Bear") == merged.lookup("Beta Wolf") == "beta-wolf"


def test_a_split_leaves_the_slug_with_one_half_and_gives_the_other_a_fresh_slug():
    together = build([A("misp", "m1", "Twin Owl"), A("misp", "m2", "Twin Owl Elder", "Twin Owl")])
    assert len(together.actors) == 1
    slug = together.actors[0].id
    split = build([A("misp", "m1", "Twin Owl"), A("misp", "m2", "Twin Owl Elder")], together.slug_entries,
                  day="2026-10-07")
    ids = sorted(a.id for a in split.actors)
    assert len(ids) == 2 and slug in ids
    other = next(i for i in ids if i != slug)
    assert other not in {e["slug"] for e in together.slug_entries}
    assert entry(split, other)["first_published"] == "2026-10-07"


def test_an_unmatched_actor_gets_a_fresh_slug_and_the_vanished_one_stays_reserved():
    first = build([A("misp", "old", "Glass Heron")], day="2026-01-01")
    second = build([A("misp", "new", "Glass Heron")], first.slug_entries, day="2026-02-01")
    assert second.actors[0].id == "glass-heron-2"
    assert entry(second, "glass-heron-2")["suffix"] == 2
    old = entry(second, "glass-heron")
    assert (old["retired"], old["merged_into"]) == (True, None)
    assert old["anchors"] == ["misp:old"]


def test_a_vanished_actor_gets_its_slug_back_when_it_returns():
    first = build([A("misp", "m1", "Glass Heron"), A("misp", "m2", "Odd Cat")], day="2026-01-01")
    gap = build([A("misp", "m2", "Odd Cat")], first.slug_entries, day="2026-02-01")
    assert active(gap) == {"odd-cat"}
    back = build([A("misp", "m1", "Glass Heron"), A("misp", "m2", "Odd Cat")], gap.slug_entries, day="2026-03-01")
    assert back.lookup("Glass Heron") == "glass-heron"
    assert entry(back, "glass-heron")["retired"] is False
    assert entry(back, "glass-heron")["first_published"] == "2026-01-01"


def test_an_actor_that_gains_an_attack_id_keeps_the_slug_it_already_published():
    # ATT&CK adding a group later must not move an address that people may have bookmarked. The
    # group ID is kept as an anchor, so the actor is still recognised, but the slug stays.
    first = build([A("misp", "m1", "Odd Bear")], day="2026-01-01")
    second = build([A("misp", "m1", "Odd Bear"), A("attack", "G0099", "Strange Group", "Odd Bear")],
                   first.slug_entries, day="2026-02-01")
    assert [a.id for a in second.actors] == ["odd-bear"]
    kept = entry(second, "odd-bear")
    assert kept["anchors"] == ["G0099", "misp:m1"]
    assert (kept["retired"], kept["merged_into"], kept["first_published"]) == (False, None, "2026-01-01")
    assert "G0099" not in {e["slug"] for e in second.slug_entries}


def test_a_new_attack_group_uses_its_group_id_as_the_slug():
    # This is the documented exception to the name-only rule, and it applies only to an actor
    # that has no published slug yet.
    first = build([A("attack", "G0099", "Strange Group")], day="2026-01-01")
    assert [a.id for a in first.actors] == ["G0099"]


def test_a_group_id_slug_stays_with_its_own_group_when_a_second_group_pulls_the_records_away():
    # ATT&CK once tracked one group, and other sources' records merged into it. A later matrix adds
    # a second group that shares a name with most of those records. The two groups cannot merge, so
    # the component splits, and the larger half must not take the first group's ID as its slug.
    first = build([A("attack", "G0035", "Dragonfly", "Energetic Bear"),
                   A("misp", "m1", "Energetic Bear", "Palmetto Fusion"),
                   A("misp", "m2", "Palmetto Fusion"), A("etda", "e1", "Palmetto Fusion")], day="2026-01-01")
    assert [a.id for a in first.actors] == ["G0035"]
    second = build([A("attack", "G0035", "Dragonfly", "Energetic Bear"), A("attack", "G1000", "ALLANITE", "Palmetto Fusion"),
                    A("misp", "m1", "Energetic Bear", "Palmetto Fusion"),
                    A("misp", "m2", "Palmetto Fusion"), A("etda", "e1", "Palmetto Fusion")],
                   first.slug_entries, day="2026-02-01")
    by_group = {next(m.source_id for m in a.members if m.source == "attack"): a.id for a in second.actors}
    assert by_group == {"G0035": "G0035", "G1000": "G1000"}
    assert len({e["slug"] for e in second.slug_entries if not e["retired"]}) == 2


def test_two_published_slugs_that_merge_into_an_attack_group_keep_the_older_one():
    first = build([A("misp", "m1", "Odd Bear"), A("misp", "m2", "Even Bear")], day="2026-01-01")
    second = build([A("misp", "m1", "Odd Bear"), A("misp", "m2", "Even Bear"),
                    A("attack", "G0099", "Strange Group", "Odd Bear", "Even Bear")], first.slug_entries, day="2026-02-01")
    [survivor] = [a.id for a in second.actors]
    assert survivor == "even-bear"
    assert (entry(second, "odd-bear")["retired"], entry(second, "odd-bear")["merged_into"]) == (True, "even-bear")


def test_a_chain_of_merges_points_at_the_last_survivor():
    one = build([A("misp", "c", "Cedar")], day="2026-01-01")
    two = build([A("misp", "a", "Ash"), A("misp", "b", "Birch"), A("misp", "c", "Cedar")],
                one.slug_entries, day="2026-02-01")
    three = build([A("misp", "a", "Ash", "Birch"), A("misp", "b", "Birch"), A("misp", "c", "Cedar")],
                  two.slug_entries, day="2026-03-01")
    assert entry(three, "birch")["merged_into"] == "ash"
    four = build([A("misp", "a", "Ash", "Birch", "Cedar"), A("misp", "b", "Birch"), A("misp", "c", "Cedar")],
                 three.slug_entries, day="2026-04-01")
    assert active(four) == {"cedar"}
    # Ash was merged into the older Cedar, so the page that pointed at Ash follows it there.
    assert entry(four, "ash")["merged_into"] == "cedar"
    assert entry(four, "birch")["merged_into"] == "cedar"


def test_an_actor_that_was_merged_away_is_not_recognised_again():
    first = build([A("misp", "m1", "Glass Heron"), A("misp", "m2", "Odd Cat")], day="2026-01-01")
    merged = build([A("misp", "m1", "Glass Heron", "Odd Cat"), A("misp", "m2", "Odd Cat")], first.slug_entries,
                   day="2026-02-01")
    assert entry(merged, "odd-cat")["merged_into"] == "glass-heron"
    # A split later: the retired address stays a redirect and is not handed back to a fragment.
    split = build([A("misp", "m1", "Glass Heron"), A("misp", "m2", "Odd Cat")], merged.slug_entries,
                  day="2026-03-01")
    assert entry(split, "odd-cat")["retired"] is True
    assert entry(split, "odd-cat")["merged_into"] == "glass-heron"
    assert split.lookup("Odd Cat") == "odd-cat-2"


# --- The run is idempotent and does not depend on record order ---------------

def _world():
    return [A("attack", "G0007", "APT28", "Sofacy"), A("misp", "m1", "Sofacy", "Fancy Bear"),
            A("misp", "m2", "Glass Heron"), A("malpedia", "p2", "Glass Heron"), A("misp", "m3", "Café Bear"),
            A("misp", "m4", "海莲花"), A("misp", "m5", "Index"), A("etda", "e1", "Hidden Otter")]


def test_two_runs_over_the_same_sources_are_byte_identical():
    shown = {"attack", "misp", "malpedia"}
    first = build(_world(), shown=shown)
    second = build(_world(), first.slug_entries, day="2026-12-01", shown=shown)
    third = build(_world(), second.slug_entries, day="2027-01-01", shown=shown)
    dump = lambda r: json.dumps(slugs.document(r.slug_entries), indent=2, ensure_ascii=False)  # noqa: E731
    assert dump(first) == dump(second) == dump(third)


def test_slugs_do_not_depend_on_the_order_of_the_records():
    shown = {"attack", "misp", "malpedia"}
    reference = build(_world(), shown=shown)
    rng = random.Random(7)
    for _ in range(10):
        records = _world()
        rng.shuffle(records)
        again = build(records, reference.slug_entries, shown=shown)
        assert again.slug_entries == reference.slug_entries
        fresh = build(records, shown=shown)
        assert fresh.slug_entries == reference.slug_entries


# --- The registry document -------------------------------------------------

def test_the_document_matches_its_schema_and_is_sorted():
    reg = build(_world(), shown={"attack", "misp", "malpedia"})
    doc = slugs.document(reg.slug_entries)
    assert list(Draft202012Validator(load_schema("slugs")).iter_errors(json.loads(json.dumps(doc)))) == []
    listed = [e["slug"] for e in doc["entries"]]
    assert listed == sorted(listed)
    for e in doc["entries"]:
        assert e["anchors"] == sorted(e["anchors"])


def test_slugs_json_sits_at_the_top_level_of_data():
    assert schema_for("slugs.json") == "slugs"
    # actors/ holds actor files only, and the validators would treat anything there as one.
    assert schema_for("actors/slugs.json") == "actor"


def test_read_registry_returns_nothing_for_a_missing_file(tmp_path):
    assert slugs.read_registry(tmp_path / "slugs.json") == []


def test_read_registry_refuses_a_file_that_breaks_the_schema(tmp_path):
    # Starting again from an empty registry would quietly change published addresses.
    path = tmp_path / "slugs.json"
    path.write_text('{"entries": [{"slug": "x"}]}', encoding="utf-8")
    with pytest.raises(ValueError, match="slugs.json"):
        slugs.read_registry(path)
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError, match="slugs.json"):
        slugs.read_registry(path)


def test_read_registry_round_trips_what_the_document_wrote(tmp_path):
    reg = build(_world(), shown={"attack", "misp", "malpedia"})
    path = tmp_path / "slugs.json"
    path.write_text(json.dumps(slugs.document(reg.slug_entries)), encoding="utf-8")
    assert slugs.read_registry(path) == reg.slug_entries


# --- Cross-checks against the published actors ------------------------------

def _doc(reg):
    return slugs.document(reg.slug_entries)


def test_cross_check_accepts_a_registry_that_matches_the_actors():
    reg = build([A("misp", "m1", "Glass Heron")])
    assert slugs.cross_problems({"glass-heron": "Glass Heron"}, _doc(reg)) == []


def test_cross_check_flags_an_actor_with_no_entry():
    reg = build([A("misp", "m1", "Glass Heron")])
    problems = slugs.cross_problems({"glass-heron": "Glass Heron", "odd-cat": "Odd Cat"}, _doc(reg))
    assert any("odd-cat" in p and "no entry" in p for p in problems)


def test_cross_check_flags_an_active_entry_that_is_not_a_published_actor():
    reg = build([A("misp", "m1", "Glass Heron"), A("misp", "m2", "Odd Cat")])
    problems = slugs.cross_problems({"glass-heron": "Glass Heron"}, _doc(reg))
    assert any("odd-cat" in p and "not a published actor" in p for p in problems)


def test_cross_check_flags_a_retired_entry_that_is_a_published_actor():
    first = build([A("misp", "old", "Glass Heron")])
    second = build([A("misp", "new", "Glass Heron")], first.slug_entries)
    problems = slugs.cross_problems({"glass-heron": "Glass Heron", "glass-heron-2": "Glass Heron"}, _doc(second))
    assert any("glass-heron" in p and "retired" in p for p in problems)


def test_cross_check_flags_a_name_that_differs_from_the_actor_file():
    reg = build([A("misp", "m1", "Glass Heron")])
    problems = slugs.cross_problems({"glass-heron": "Crystal Heron"}, _doc(reg))
    assert any("glass-heron" in p and "Crystal Heron" in p for p in problems)


def test_cross_check_flags_duplicate_slugs_bad_merges_and_bad_suffixes():
    reg = build([A("misp", "m1", "Glass Heron")])
    good = _doc(reg)["entries"][0]
    bad = {"entries": [good, {**good, "anchors": ["misp:x"]}]}
    assert any("twice" in p for p in slugs.cross_problems({"glass-heron": "Glass Heron"}, bad))
    dangling = {"entries": [good, {**good, "slug": "old-owl", "retired": True, "merged_into": "nobody"}]}
    assert any("nobody" in p for p in slugs.cross_problems({"glass-heron": "Glass Heron"}, dangling))
    live_merge = {"entries": [{**good, "merged_into": "glass-heron"}]}
    assert any("merged_into" in p for p in slugs.cross_problems({"glass-heron": "Glass Heron"}, live_merge))
    wrong_suffix = {"entries": [{**good, "suffix": 3}]}
    assert any("suffix" in p for p in slugs.cross_problems({"glass-heron": "Glass Heron"}, wrong_suffix))
    unsorted = {"entries": [{**good, "anchors": ["misp:b", "misp:a"]}]}
    assert any("sorted" in p for p in slugs.cross_problems({"glass-heron": "Glass Heron"}, unsorted))


def test_cross_check_flags_a_slug_that_two_entries_claim_through_a_merge_loop():
    reg = build([A("misp", "m1", "Glass Heron")])
    good = _doc(reg)["entries"][0]
    loop = {"entries": [{**good, "slug": "a-1", "retired": True, "merged_into": "b-1"},
                        {**good, "slug": "b-1", "retired": True, "merged_into": "a-1"}]}
    assert any("chain" in p for p in slugs.cross_problems({}, loop))
