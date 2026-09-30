"""guesses.json: the model, its evaluation, and the promises that a guess changes nothing else."""
import json
import math

import pytest

from aptx.build import guesses as g
from aptx.build.contract import validator
from aptx.core.models import ActorRecord, ReportRecord, SoftwareRecord
from aptx.resolve import similarity as sim
from aptx.resolve.registry import resolve

NOW = "2026-09-29"

ACTOR_WORDS = ["sofacy", "turla", "lazarus", "kimsuky", "winnti", "carbanak", "oilrig", "sidewinder", "gamaredon",
               "sandworm", "equation", "darkhotel", "patchwork", "bitter", "transparent", "molerats", "cobalt",
               "naikon", "menupass", "tonto", "dragonfly", "energetic", "buhtrap", "silence", "machete", "gorgon",
               "inception", "windshift", "evilnum", "higaisa"]
MALWARE_WORDS = ["zorklo", "quixel", "brambo", "vexlin", "tarnok", "plumbe", "dritan", "wexham", "yorbel", "cindro",
                 "hathor", "ulvane"]


def A(src, sid, name, *aliases):
    return ActorRecord(source=src, source_id=sid, name=name, aliases=list(aliases), retrieved_at=NOW)


def S(src, sid, name, kind):
    return SoftwareRecord(source=src, source_id=sid, name=name, aliases=[], kind=kind, retrieved_at=NOW)


def R(sid, names, source="paper"):
    return ReportRecord(source=source, source_id=sid, title="t", date_basis="publisher", actor_names=list(names),
                        retrieved_at=NOW)


def L(name, label, status="derived"):
    return g.Label(name, label, status, "test")


class World:
    """30 actors, each also spelled "APT <name>" by a source, and 12 malware families ending in "Loader"."""

    def __init__(self, extra_actors=(), reports=(), shown_sources=None):
        self.actors = [A("attack", f"G{1000 + i}", w.title(), f"APT {w.title()}") for i, w in enumerate(ACTOR_WORDS)]
        self.actors += list(extra_actors)
        self.software = [S("malpedia", f"win.{w}", f"{w.title()} Loader", "malware") for w in MALWARE_WORDS]
        self.registry = resolve(self.actors, self.software)
        self.reports = list(reports)
        self.shown_sources = shown_sources
        self.labels = [L(f"APT {w.title()}", "actor") for w in ACTOR_WORDS]
        self.labels += [L(f"{w.title()} Loader", "malware") for w in MALWARE_WORDS]
        self.published = {a.id: a.name for a in self.registry.actors}

    def build(self, unresolved, labels=None):
        return g.build_guesses(self.registry, self.software, self.reports, unresolved,
                               self.labels if labels is None else labels, self.published, self.shown_sources)


def row(name, count=1, typed=None):
    return {"name": name, "count": count, "typed_as": typed}


def by_name(payload):
    return {x["name"]: x for x in payload["guesses"]}


# The logistic regression

def test_solve_finds_the_solution_of_a_small_system():
    x = g._solve([[2.0, 1.0], [1.0, 3.0]], [5.0, 10.0])
    assert x == pytest.approx([1.0, 3.0])


def test_the_fit_learns_a_signal_that_separates_the_labels():
    rows = [[1.0]] * 8 + [[0.0]] * 8
    y = [1] * 8 + [0] * 8
    w = g.fit_logistic(rows, y)
    assert g.predict_logistic(w, [1.0]) > 0.7 and g.predict_logistic(w, [0.0]) < 0.3


def test_the_penalty_keeps_the_weights_finite_when_a_signal_never_disagrees():
    w = g.fit_logistic([[1.0]] * 5 + [[0.0]] * 5, [1] * 5 + [0] * 5)
    assert all(math.isfinite(x) and abs(x) < 30 for x in w)


def test_the_intercept_of_a_signal_free_model_is_the_base_rate():
    w = g.fit_logistic([[0.0]] * 10, [1] * 3 + [0] * 7)
    assert g.predict_logistic(w, [0.0]) == pytest.approx(0.3, abs=0.01)


# Bands and calibration

def test_the_band_follows_the_confidence_and_a_silent_name_is_always_low():
    assert g.band_for(0.9, True) == "high" and g.band_for(0.85, True) == "high"
    assert g.band_for(0.75, True) == "medium" and g.band_for(0.5, True) == "low"
    assert g.band_for(0.99, False) == "low"


def test_calibration_never_gives_a_higher_score_a_lower_confidence():
    # Bin 0.85 to 1 is worse than bin 0.7 to 0.85 here, so it must be lifted to at least the earlier one.
    rows = [(0.6, True, True)] * 4 + [(0.75, True, True)] * 20 + [(0.9, False, True)] * 5
    bins, _ = g._calibrate(rows)
    values = [v for _, v in bins]
    assert values == sorted(values)


def test_the_no_signal_confidence_comes_from_silent_names_only():
    rows = [(0.9, False, True)] * 10 + [(0.7, True, False)] * 10
    bins, no_signal = g._calibrate(rows)
    assert no_signal > 0.8 and bins[0][1] == 0.6


# The evaluation

def test_too_little_ground_truth_gives_no_fit():
    world = World()
    assert g.fit(world.labels[:5], sim.only_actors(sim.build_reference(world.registry, world.software, []),
                                                   world.published), world.registry.lookup) is None


def test_a_single_class_gives_no_fit():
    world = World()
    ref = sim.build_reference(world.registry, world.software, [])
    assert g.fit([x for x in world.labels if x.label == "actor"], ref, world.registry.lookup) is None


def test_the_evaluation_is_scored_leave_one_out_and_matches_the_ground_truth():
    world = World()
    payload = world.build([])
    ev = payload["evaluation"]
    assert ev["ground_truth"]["n"] == 42 and ev["ground_truth"]["derived"] == 42
    assert {c["label"]: c["count"] for c in ev["ground_truth"]["by_label"]} == {"actor": 30, "malware": 12, "tool": 0, "not-an-entity": 0}
    assert ev["correct"] <= ev["ground_truth"]["n"] and 0 <= ev["accuracy"] <= 1
    assert ev["baselines"]["majority_label"] == "actor"
    assert ev["baselines"]["majority_accuracy"] == pytest.approx(30 / 42, abs=0.001)
    # Every name here is a variant of a real actor name, so the proposals are all right.
    kinds = {k["kind"]: k for k in ev["matching"]["by_kind"]}
    assert kinds["variant"]["precision"] == 1.0 and kinds["variant"]["published"] is True


def test_labels_with_few_known_names_are_not_validated():
    ev = World().build([])["evaluation"]
    stats = {s["label"]: s for s in ev["per_label"]}
    assert stats["actor"]["validated"] and stats["malware"]["validated"]
    assert not stats["tool"]["validated"] and not stats["not-an-entity"]["validated"]


def test_the_evaluation_says_which_signal_it_cannot_measure():
    ev = World().build([])["evaluation"]
    assert any(u["signal"] == "exact_name_listed" for u in ev["unmeasured_signals"])


def test_pending_rows_never_change_the_evaluation():
    world = World()
    pending = [L("Foo Group", "malware", "pending"), L("Zed", "tool", "pending"), L("Operation Q", "actor", "pending")]
    assert world.build([], world.labels)["evaluation"] == world.build([], world.labels + pending)["evaluation"]


def test_a_derived_label_the_sources_do_not_support_is_not_ground_truth():
    world = World()
    ghost = [L("Ghost Loader", "malware"), L("APT Nobody", "actor")]
    assert world.build([], world.labels + ghost)["evaluation"]["ground_truth"]["n"] == 42


def test_confirmed_rows_join_the_ground_truth():
    world = World()
    ev = world.build([], world.labels + [L("Newname", "actor", "confirmed")])["evaluation"]
    assert ev["ground_truth"]["confirmed"] == 1 and ev["ground_truth"]["n"] == 43


# The guesses

def test_no_labels_means_no_evaluation_and_no_guesses():
    world = World()
    assert world.build([row("Foo")], labels=[]) == {"evaluation": None, "guesses": []}


def test_a_name_that_a_source_types_as_software_is_not_guessed():
    assert World().build([row("Emotet", 9, "malware")])["guesses"] == []


def test_two_spellings_of_one_name_make_one_guess_with_their_counts_added():
    payload = World().build([row("Iron Group", 3), row("iron group", 2)])
    [guess] = payload["guesses"]
    assert guess["name"] == "Iron Group" and guess["count"] == 5


def test_a_derived_name_is_not_guessed_again():
    assert World().build([row("APT Sofacy", 4)])["guesses"] == []


def test_a_confirmed_name_keeps_its_label_and_carries_no_confidence():
    world = World()
    labels = world.labels + [L("Kittenfoo", "actor", "confirmed")]
    [guess] = world.build([row("Kittenfoo", 2)], labels)["guesses"]
    assert (guess["label"], guess["band"], guess["confidence"], guess["status"]) == ("actor", "confirmed", None, "confirmed")
    assert guess["evidence"] == [] and guess["matched_actor_id"] is None


def test_a_variant_of_a_known_actor_is_proposed_as_that_actor():
    world = World()
    [guess] = world.build([row("Sofacy Gang", 7)])["guesses"]
    sofacy = world.registry.lookup("Sofacy")
    assert guess["label"] == "actor" and guess["matched_actor_id"] == sofacy
    assert guess["matched_actor_name"] == "Sofacy"
    assert guess["confidence"] is not None and guess["band"] in {"high", "medium", "low"}
    assert guess["status"] == "pending confirmation"
    assert any(e["signal"] == "actor_resemblance" and "Sofacy" in e["detail"] for e in guess["evidence"])


def test_an_actor_that_is_not_published_is_never_proposed():
    world = World()
    sofacy = world.registry.lookup("Sofacy")
    world.published = {k: v for k, v in world.published.items() if k != sofacy}
    [guess] = world.build([row("Sofacy Gang")])["guesses"]
    assert guess["matched_actor_id"] is None
    assert "Sofacy" not in json.dumps(guess["evidence"])


def test_a_name_that_ends_in_a_malware_word_is_guessed_as_malware():
    [guess] = World().build([row("Blorp Loader", 3)])["guesses"]
    assert guess["label"] == "malware" and guess["matched_actor_id"] is None
    assert any(e["signal"] == "malware_word" for e in guess["evidence"])


def test_a_campaign_name_and_a_placeholder_are_rules_and_unvalidated():
    payload = World().build([row("Operation Zeta"), row("Unknown")])
    for name, signal in (("Operation Zeta", "campaign_word"), ("Unknown", "placeholder_word")):
        guess = by_name(payload)[name]
        assert (guess["label"], guess["band"], guess["confidence"]) == ("not-an-entity", "unvalidated", None)
        assert guess["evidence"][0]["signal"] == signal and guess["evidence"][0]["weight"] is None


def test_a_name_that_two_actors_share_is_an_actor_by_rule_and_unvalidated():
    both = [A("attack", "G2001", "Alpha Team", "Shared Alias"), A("attack", "G2002", "Beta Team", "Shared Alias")]
    world = World(extra_actors=both)
    assert world.registry.lookup("Shared Alias") is None
    [guess] = world.build([row("Shared Alias", 2)])["guesses"]
    assert (guess["label"], guess["band"], guess["confidence"]) == ("actor", "unvalidated", None)
    assert guess["evidence"][0]["signal"] == "exact_actor_name"
    assert "ATT&CK" in guess["evidence"][0]["detail"]


def test_a_name_with_no_signal_gets_the_base_rate_and_the_low_band():
    [guess] = World().build([row("Plainname", 1)])["guesses"]
    assert guess["band"] == "low"
    assert guess["evidence"][0]["signal"] == "base_rate" and "30 of 42" in guess["evidence"][0]["detail"]


def test_co_occurrence_with_a_known_actor_appears_as_context_with_no_weight():
    world = World(reports=[R("p1", ["Cooc Name", "Sofacy"])])
    [guess] = world.build([row("Cooc Name")])["guesses"]
    item = next(e for e in guess["evidence"] if e["signal"] == "cooc_actor")
    assert item["weight"] is None and "Sofacy" in item["detail"]


def test_orkl_never_appears_in_the_evidence_or_the_signals():
    world = World(reports=[R("o1", ["Tagname", "Sofacy"], source="orkl")])
    payload = world.build([row("Tagname"), row("Sofacy Gang")])
    assert "orkl" not in json.dumps(payload).casefold()
    assert all(e["signal"] != "cooc_actor" for x in payload["guesses"] for e in x["evidence"])


def test_names_from_a_source_that_may_not_be_shown_never_reach_a_guess():
    extra = [A("etda", "e1", "Sofacy", "Zebrocy Team")]
    world = World(extra_actors=extra, shown_sources={"attack", "malpedia", "paper"})
    payload = world.build([row("Zebrocy Squad")])
    assert "Zebrocy" not in json.dumps([e for x in payload["guesses"] for e in x["evidence"]])


def test_the_most_reported_names_come_first():
    payload = World().build([row("Aaa", 1), row("Zzz", 9), row("Mmm", 4)])
    assert [x["name"] for x in payload["guesses"]] == ["Zzz", "Mmm", "Aaa"]


def test_the_output_matches_the_schema():
    world = World(reports=[R("p1", ["Cooc Name", "Sofacy"])])
    both = [row("Sofacy Gang", 7), row("Blorp Loader"), row("Operation Zeta"), row("Unknown"), row("Plainname"),
            row("Cooc Name"), row("Kittenfoo")]
    labels = world.labels + [L("Kittenfoo", "actor", "confirmed"), L("Pend", "tool", "pending")]
    payload = world.build(both, labels)
    assert [e.message for e in validator("guesses").iter_errors(payload)] == []
    empty = {"evaluation": None, "guesses": []}
    assert [e.message for e in validator("guesses").iter_errors(empty)] == []


def test_a_guess_never_changes_the_registry():
    world = World()
    before = (world.registry.stats(), [(a.id, a.name, len(a.aliases)) for a in world.registry.actors],
              world.registry.lookup("Sofacy Gang"), world.registry.lookup("Blorp Loader"))
    world.build([row("Sofacy Gang", 7), row("Blorp Loader")])
    after = (world.registry.stats(), [(a.id, a.name, len(a.aliases)) for a in world.registry.actors],
             world.registry.lookup("Sofacy Gang"), world.registry.lookup("Blorp Loader"))
    assert before == after


# Comparing with the hand-made guesses

def test_the_comparison_lists_disagreements_and_never_scores_the_pending_rows():
    world = World()
    payload = world.build([row("Sofacy Gang", 7), row("Blorp Loader")])
    pending = [L("Sofacy Gang", "actor", "pending"), L("Blorp Loader", "actor", "pending"), L("Other", "tool", "pending"),
               L("APT Turla", "actor")]
    out = g.compare_pending(payload, pending)
    assert out["compared"] == 2 and out["agree"] == 1 and out["rate"] == 0.5
    assert [d["name"] for d in out["disagreements"]] == ["Blorp Loader"]


# The bundled labels

def test_the_labels_file_is_read_with_its_statuses():
    labels = g.read_labels()
    assert labels and {x.status for x in labels} <= {"derived", "pending", "confirmed"}
    assert {x.label for x in labels} <= set(g.LABELS)


def test_reading_a_missing_labels_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        g.read_labels(tmp_path / "none.csv")


# The build wiring

def _store(tmp_path):
    from pathlib import Path

    from aptx.build.notice import SOURCE_ORDER
    from aptx.core.snapshot import SnapshotStore
    fixtures = Path(__file__).parent / "fixtures"
    store = SnapshotStore(tmp_path / "cache")
    store.save("attack", "enterprise-attack.json", (fixtures / "attack_min.json").read_bytes())
    licence = "\"© 2026 The MITRE Corporation. This work is reproduced and distributed with the permission of The MITRE Corporation.\"\n"
    store.save("attack", "LICENSE.txt", licence.encode("utf-8"))
    for key in SOURCE_ORDER:
        if key != "attack":
            store.save(key, "marker", b"x")
    return store


def _connectors():
    from aptx.build.notice import SOURCE_ORDER
    from aptx.core.models import SourceBundle
    from aptx.sources.base import Connector

    class Quiet(Connector):
        def __init__(self, name):
            self.name = name

        def fetch(self, store):
            pass

        def normalize(self, store):
            return SourceBundle(source=self.name)

        def policy(self, store, sources_md=None):
            return "full"

    return [Quiet(key) for key in SOURCE_ORDER]


def test_a_build_writes_a_valid_guesses_file_even_with_no_ground_truth(tmp_path):
    from aptx import cli
    out = tmp_path / "data"
    cli.run(out, _store(tmp_path), _connectors(), fetch=False, generated_at="2026-09-30T04:00:00Z")
    payload = json.loads((out / "guesses.json").read_text(encoding="utf-8"))
    assert payload == {"evaluation": None, "guesses": []}


def test_a_build_without_a_labels_file_still_works(tmp_path):
    from aptx import cli
    out = tmp_path / "data"
    cli.run(out, _store(tmp_path), _connectors(), fetch=False, labels=tmp_path / "missing.csv",
            generated_at="2026-09-30T04:00:00Z")
    assert json.loads((out / "guesses.json").read_text(encoding="utf-8"))["guesses"] == []
