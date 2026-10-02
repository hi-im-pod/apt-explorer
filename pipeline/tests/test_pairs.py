"""Name pairs a vendor post states, and which of them may add an alias or an actor."""
import pytest

from aptx.resolve import pairs


def found(text):
    return pairs.extract(text)


@pytest.mark.parametrize("text,expected", [
    ("JADEPUFFER, tracked by Microsoft as Storm-3168, abused service principals.", [("JADEPUFFER", "Storm-3168")]),
    ("Zorklo (also known as Marigold Typhoon) targets banks.", [("Zorklo", "Marigold Typhoon")]),
    ("The actor Larkspur, a.k.a. UNC9999, returned.", [("Larkspur", "UNC9999")]),
    ("Larkspur, which Cisco Talos tracks as UAT-1234, was active.", [("Larkspur", "UAT-1234")]),
    ("Larkspur, also dubbed “Nightjar”, spreads.", [("Larkspur", "Nightjar")]),
])
def test_a_phrase_that_equates_two_names_is_a_pair(text, expected):
    assert found(text) == expected


@pytest.mark.parametrize("text", [
    "UAT-11587 overlaps with Jewelbug in tooling.",
    "Larkspur is similar to Nightjar and linked to Marigold.",
    "We track this activity as UAT-1234 and it differs from Jewelbug.",
    "The group, known as the Microsoft Defender team, wrote it.",
    "Larkspur, also known as it, is back.",
    "Larkspur, known as 12345, is back.",
])
def test_a_phrase_that_does_not_equate_two_names_is_not_a_pair(text):
    assert found(text) == []


def test_a_pair_is_listed_once_in_either_order():
    text = "Larkspur, also known as Nightjar. Later, Nightjar, also known as Larkspur."
    assert found(text) == [("Larkspur", "Nightjar")]


def test_a_vendor_cluster_id_is_never_the_name_an_actor_is_shown_under():
    d = pairs.Decision(("Storm-3168", "JADEPUFFER"), True, "new", "")
    assert (d.primary, d.alias) == ("JADEPUFFER", "Storm-3168")
    d = pairs.Decision(("Larkspur", "UNC9999"), True, "new", "")
    assert (d.primary, d.alias) == ("Larkspur", "UNC9999")


@pytest.mark.parametrize("name,yes", [("Storm-3168", True), ("UNC2452", True), ("UAT 11587", True), ("CL-STA-0048", True), ("GTG-20006", True),
                                      ("JadePuffer", False), ("APT28", False)])
def test_cluster_ids(name, yes):
    assert pairs.is_cluster_id(name) is yes


REGISTRY = {"Larkspur": "a1", "Nightjar": "a2", "Zorklo": "a3"}
lookup = REGISTRY.get
software = {"Cosmic": "malware"}.get
PUBLISHED = {"a1", "a2"}


def decide(*pair, guess=None, published=PUBLISHED):
    [d] = pairs.select([pair], lookup, software, published, guess)
    return d


def test_one_published_actor_and_one_new_name_is_a_bridge():
    d = decide("Larkspur", "Storm-1")
    assert (d.accepted, d.kind) == (True, "bridge")
    assert decide("Storm-1", "Larkspur").accepted


def test_a_name_known_only_as_an_unpublished_actor_counts_as_unknown():
    assert not decide("Zorklo", "Storm-1").accepted


def test_two_names_of_one_actor_add_nothing():
    d = decide("Larkspur", "Larkspur")
    assert (d.accepted, d.kind) == (False, "known")


def test_two_published_actors_are_never_joined():
    d = decide("Larkspur", "Nightjar")
    assert not d.accepted and "two different actors" in d.reason


def test_a_malware_name_never_becomes_an_actor_or_alias():
    for pair in (("Cosmic", "Storm-1"), ("Larkspur", "Cosmic")):
        d = decide(*pair)
        assert (d.accepted, d.kind) == (False, "software")


def actor_guess(label="actor"):
    return lambda name: {"label": label}


def test_two_new_names_need_a_cluster_id_and_a_guesser_that_calls_both_actors():
    assert decide("Newcomer", "Storm-9", guess=actor_guess()).accepted
    assert not decide("Newcomer", "Storm-9", guess=actor_guess("malware")).accepted
    assert not decide("Newcomer", "Storm-9", guess=lambda n: None).accepted
    assert not decide("Newcomer", "Storm-9").accepted


def test_the_guesser_alone_does_not_promote_two_new_names():
    d = decide("Newcomer", "Otherthing", guess=actor_guess())
    assert not d.accepted and "cluster ID" in d.reason
