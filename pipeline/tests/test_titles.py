import pytest

from aptx.resolve import titles

ALIASES = {
    "G0007": ["APT28", "Fancy Bear", "Sofacy", "Forest Blizzard", "STRONTIUM"],
    "G1033": ["Star Blizzard", "SEABORGIUM", "Callisto"],
    "G0094": ["Kimsuky", "Velvet Chollima"],
    "G0064": ["Equation Group", "Equation"],
    "G0089": ["Hacking Team"],
    "G0100": ["Cobalt Group", "Cobalt"],
    "G0200": ["Lazarus Group", "Lazarus"],
    "G0300": ["Panda"],
    "G0400": ["Konni", "Opal Sleet"],
    "G0500": ["Storm-0558"],
    "G0600": ["Shared Name"],
    "G0601": ["Shared Name"],
}
SOFTWARE = {"cobaltstrike", "mimikatz"}


def lookup(name):
    key = titles.norm(name)
    hits = {a for a, values in ALIASES.items() if any(titles.norm(v) == key for v in values)}
    return next(iter(hits)) if len(hits) == 1 else None


@pytest.fixture(scope="module")
def matcher():
    return titles.build(ALIASES, lookup, lambda phrase: titles.norm(phrase) in SOFTWARE)


@pytest.mark.parametrize("title, expected", [
    ("Star Blizzard targets civil society with new tooling", {"G1033"}),
    ("Storm-0558 acquired a signing key", {"G0500"}),
    ("APT28 and Fancy Bear are the same actor", {"G0007"}),
    ("Forest Blizzard (STRONTIUM) exploits CVE-2023-23397", {"G0007"}),
    ("Kimsuky's new backdoor", {"G0094"}),
    ("Lazarus Group's latest campaign", {"G0200"}),
    ("Hacking Team leaked", {"G0089"}),
    ("The Equation Group arsenal", {"G0064"}),
    ("APT28 versus Star Blizzard", {"G0007", "G1033"}),
])
def test_a_title_names_the_actor_it_says(matcher, title, expected):
    assert matcher.match(title) == expected


@pytest.mark.parametrize("title", [
    "Panda bears at the zoo",
    "Hacking tools of 2025",
    "Equation solving for beginners",
    "A silent Cobalt moment",
])
def test_one_ordinary_word_is_not_a_name_on_its_own(matcher, title):
    assert matcher.match(title) == set()


def test_a_long_word_that_is_not_ordinary_is_a_name_on_its_own(matcher):
    assert matcher.match("Lazarus rises") == {"G0200"}
    assert matcher.match("Callisto moon photos") == {"G1033"}


def test_software_consumes_its_words_so_it_does_not_name_a_group(matcher):
    assert matcher.match("Cobalt Strike beacons in the wild") == set()
    assert matcher.match("Cobalt Group deploys Cobalt Strike") == {"G0100"}


def test_an_alias_two_actors_share_names_neither(matcher):
    assert matcher.match("Shared Name returns") == set()


def test_a_name_that_is_malware_never_matches(matcher):
    assert matcher.match("Konni RAT is back") == set()
    assert matcher.match("Opal Sleet uses Konni") == {"G0400"}


def test_only_whole_words_match(matcher):
    assert matcher.match("APT280 and Kimsukyy") == set()
    assert matcher.match("Fancy Bearings catalogue") == set()


def test_case_and_punctuation_do_not_matter(matcher):
    assert matcher.match("star-blizzard: new TTPs") == {"G1033"}
    assert matcher.match("STAR BLIZZARD") == {"G1033"}


def test_an_empty_matcher_matches_nothing_and_is_falsy():
    empty = titles.build({}, lambda name: None, lambda phrase: False)
    assert not empty
    assert empty.match("Star Blizzard") == set()


def test_an_alias_that_does_not_resolve_to_its_own_actor_is_dropped():
    built = titles.build({"G1": ["Zebra Crew"]}, lambda name: "G2", lambda phrase: False)
    assert not built


@pytest.mark.parametrize("alias, usable", [
    ("Star Blizzard", True), ("APT28", True), ("TA505", True), ("Bear", False),
    ("Panda", False), ("12345", False), ("", False), ("Konni", False), ("APT1", True), ("UN1", False),
    ("Fancy Bear", True), ("Hacking Team", True),
])
def test_which_aliases_are_specific_enough(alias, usable):
    assert titles._usable(alias) is usable


def test_a_name_made_of_one_ordinary_word_and_group_needs_the_aliass_own_words(matcher):
    assert matcher.match("Russian hacking group APT28") == {"G0007"}
    assert matcher.match("Hacking Group leaks") == set()
    assert matcher.match("Hacking Team leaks") == {"G0089"}
    assert matcher.match("Lazarus Team and Lazarus Group") == {"G0200"}


def test_an_ordinary_phrase_that_is_an_alias_never_matches():
    built = titles.build({"G1": ["Copy-Paste"]}, lambda name: "G1", lambda phrase: False)
    assert not built
