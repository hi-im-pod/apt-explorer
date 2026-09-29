from aptx.extract.ids import find_cves, find_techniques, technique_candidates


def test_cves_are_normalized_and_deduplicated():
    t = "exploits cve-2023-23397 and CVE-2023-23397, also CVE-2021-40444."
    assert find_cves(t) == ["CVE-2021-40444", "CVE-2023-23397"]


def test_techniques_only_when_valid():
    t = "uses T1059.001 and T1566, see also T9999 and ST1059"
    assert find_techniques(t, valid={"T1059.001", "T1566"}) == ["T1059.001", "T1566"]


# Beyond the plan's two cases. Report text comes from PDF extraction, which
# brings typographic hyphens, glued words and missing text.

def test_cves_written_with_typographic_hyphens_are_found():
    # PDFs often set IDs with a non-breaking hyphen (U+2011) or an en dash.
    t = "CVE‑2021‑40444 and CVE–2022–30190"
    assert find_cves(t) == ["CVE-2021-40444", "CVE-2022-30190"]


def test_cve_inside_a_longer_token_is_not_a_cve():
    # A letter glued to the front, or more than seven sequence digits, means
    # the token is something else.
    assert find_cves("XCVE-2021-40444 CVE-2021-404441234 CVE-21-4044") == []


def test_candidates_keep_every_well_formed_id_and_skip_glued_ones():
    t = "T1566. T9999, T1059.001 (ST1059) T1059.001 T10590"
    assert technique_candidates(t) == ["T1059.001", "T1566", "T9999"]


def test_a_sub_technique_is_not_accepted_through_its_parent():
    # Only IDs in the valid set count, so a retired or mistyped sub-technique
    # never passes because its parent technique exists.
    assert find_techniques("T1059.999 and T1059", valid={"T1059"}) == ["T1059"]


def test_missing_text_yields_nothing():
    assert find_cves(None) == []
    assert technique_candidates("") == []
    assert find_techniques(None, valid={"T1566"}) == []
