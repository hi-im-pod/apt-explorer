import re

import pytest

from aptx.resolve.names import norm, slug

# The slug half of the actorId pattern in the resolution, actor and index
# schemas. The registry tests check full IDs against the schema itself.
SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def test_case_punctuation_space_and_width_variants_collapse():
    keys = {norm(x) for x in ["Lazarus Group", "LAZARUS", "Lazarus-Group", "lazarus  group", "Ｌａｚａｒｕｓ"]}
    assert keys == {"lazarus"}


def test_review_focus_lazarus_spellings_share_one_key():
    variants = [
        "Lazarus Group", "LAZARUS", "Lazarus-Group", "lazarus  group",
        " Lazarus Group ", "LAZARUS GROUP", "Lazarus\tGroup", "Lazarus–Group",
        "Ｌａｚａｒｕｓ",                   # full-width letters
        "Ｌａｚａｒｕｓ　Ｇｒｏｕｐ",         # full-width letters and ideographic space
        "Ｌａｚａｒｕｓ－Ｇｒｏｕｐ",         # full-width hyphen-minus
    ]
    assert {norm(v) for v in variants} == {"lazarus"}


def test_digits_are_significant():
    assert norm("APT 28") == norm("APT28") == "apt28"
    assert norm("APT2") != norm("APT28")


def test_review_focus_apt28_spellings_collapse_but_apt2_stays_distinct():
    assert {norm(v) for v in ["APT 28", "APT28", "apt-28", "Apt.28", "ＡＰＴ２８", "ＡＰＴ　２８"]} == {"apt28"}
    assert norm("APT2") == norm("APT 2") == "apt2"
    assert norm("APT2") != norm("APT 28")


def test_team_suffix_only_stripped_when_something_remains():
    assert norm("Ajax Security Team") == "ajaxsecurity"
    assert norm("Team") == "team"


def test_group_suffix_is_only_stripped_as_the_last_token():
    assert norm("Group") == "group"
    assert norm("Group 72") == "group72"
    assert norm("Group-IB") == "groupib"


def test_other_scripts_are_case_folded_not_transliterated():
    assert norm("ЛАЗАРУС") == norm("лазарус") == "лазарус"
    # casefold() rather than lower(): Greek final sigma folds to the same key.
    assert norm("ΣΊΣΥΦΟΣ") == norm("σίσυφος")


def test_names_with_no_letters_or_digits_have_no_key():
    assert norm("") == ""
    assert norm(" -- ") == ""
    assert norm("???") == ""


@pytest.mark.parametrize("name, expected", [
    ("Glass Heron", "glass-heron"),
    ("APT 28", "apt-28"),
    ("--APT 28!!", "apt-28"),
    ("Café Bear", "cafe-bear"),
    ("Łódź Spider", "lodz-spider"),
    ("Ørsted Kitten", "orsted-kitten"),
    ("Foo_Bar", "foo-bar"),
    ("Ｌａｚａｒｕｓ　Ｇｒｏｕｐ", "lazarus-group"),
    ("Straße", "strasse"),
])
def test_slug_folds_to_lowercase_ascii_words(name, expected):
    assert slug(name) == expected


def test_slug_is_empty_when_nothing_folds_to_ascii():
    # The registry falls back to another name or a hash in this case.
    assert slug("海莲花") == ""
    assert slug("Лазарь") == ""
    assert slug("???") == ""


@pytest.mark.parametrize("name", [
    "Lazarus_Group", "İstanbul Kitten", "ǅemal", "Æther", "x" * 80, "a--b__c", "Ｇ０００７",
    "été", "١٢٣ Team", "Þorn", "ﬁnance ﬂag",
])
def test_every_non_empty_slug_matches_the_actor_id_pattern(name):
    s = slug(name)
    assert s == "" or SLUG.fullmatch(s), s
