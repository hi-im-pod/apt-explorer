"""The compact reports index the explore page loads instead of every report shard."""
import copy
import hashlib
import json

import pytest

from aptx.build.report_index import build_reports_index, short_id

BUILT_AT = "2026-09-28T03:21:05Z"


def report(rid, title="A title", published="2024-05-01", org=None, actors=(), cves=(), techniques=(),
           sources=("misp",)):
    return {
        "id": rid, "title": title, "published": published,
        "date_basis": "publisher" if published else "unknown", "organisation": org,
        "url": None, "url_ok": None, "archive_url": None, "actors": list(actors),
        "actor_names_unresolved": [], "cves": list(cves), "techniques": list(techniques),
        "sources": list(sources),
    }


def sha(n):
    # Real ids are SHA-1 digests, so their leading characters differ. A zero-padded counter would not.
    return hashlib.sha1(str(n).encode()).hexdigest()


def build(reports, kev=()):
    return build_reports_index(reports, kev_cves=set(kev), built_at=BUILT_AT)


def test_rows_are_ordered_newest_first_with_undated_last():
    rows = [
        report(sha(3), published=None),
        report(sha(2), published="2023-01-01"),
        report(sha(1), published="2024-01-01"),
        report(sha(4), published="2024-01-02"),
    ]
    idx = build(rows)
    assert idx["columns"]["published"] == ["2024-01-02", "2024-01-01", "2023-01-01", None]
    assert idx["total"] == 4


def test_reports_of_one_day_are_ordered_by_title_ignoring_case_then_by_id():
    rows = [report(sha(1), "beta"), report(sha(2), "Alpha"), report(sha(3), "alpha"), report(sha(4), "Zulu")]
    idx = build(rows)
    same_title = sorted([sha(2), sha(3)])
    assert [t.casefold() for t in idx["columns"]["title"]] == ["alpha", "alpha", "beta", "zulu"]
    assert [i[:8] for i in idx["columns"]["id"]][:2] == [i[:8] for i in same_title]
    assert sorted(idx["columns"]["title"][:2]) == ["Alpha", "alpha"]


def test_ids_are_the_shortest_prefix_that_keeps_every_sha_unique():
    a = "abcdef0123" + "0" * 30
    b = "abcdef0123" + "1" * 30
    idx = build([report(a), report(b), report(sha(9))])
    assert idx["id_len"] == 11
    assert idx["columns"]["id"].count(a[:11]) == 1
    assert len(set(idx["columns"]["id"])) == 3


def test_the_prefix_never_gets_shorter_than_eight_characters():
    idx = build([report(sha(1)), report(sha(2))])
    assert idx["id_len"] == 8


def test_an_id_that_is_not_a_sha_is_kept_whole():
    idx = build([report("paper:2019_x.pdf"), report(sha(1))])
    assert "paper:2019_x.pdf" in idx["columns"]["id"]
    assert short_id("paper:2019_x.pdf", 8) == "paper:2019_x.pdf"
    assert short_id(sha(1), 8) == sha(1)[:8]


def test_strings_are_interned_and_sources_become_a_bitmask():
    rows = [
        report(sha(1), org="Acme", sources=("misp", "orkl"), actors=("G0007",), cves=("CVE-2023-1234",),
               techniques=("T1059",)),
        report(sha(2), org="Acme", sources=("orkl",), actors=("G0007", "apt-x"), published="2023-01-01"),
    ]
    idx = build(rows)
    t = idx["tables"]
    assert t["organisations"] == ["Acme"]
    assert set(t["sources"]) == {"misp", "orkl"}
    assert t["actors"][0] == "G0007"
    misp = 1 << t["sources"].index("misp")
    orkl = 1 << t["sources"].index("orkl")
    assert idx["columns"]["sources"] == [misp | orkl, orkl]
    assert idx["columns"]["organisation"] == [0, 0]
    assert [[t["actors"][i] for i in a] for a in idx["columns"]["actors"]] == [["G0007"], ["G0007", "apt-x"]]
    assert [[t["cves"][i] for i in a] for a in idx["columns"]["cves"]] == [["CVE-2023-1234"], []]


def test_a_report_with_no_organisation_gets_null():
    idx = build([report(sha(1))])
    assert idx["columns"]["organisation"] == [None]
    assert idx["tables"]["organisations"] == []


def test_kev_lists_the_cves_the_catalogue_knows_as_table_positions():
    rows = [report(sha(1), cves=("CVE-2021-1", "CVE-2022-2")), report(sha(2), cves=("CVE-2023-3",), published="2023-01-01")]
    idx = build(rows, kev={"CVE-2022-2", "CVE-2099-9"})
    assert [idx["tables"]["cves"][i] for i in idx["kev"]] == ["CVE-2022-2"]


def test_every_column_has_one_entry_per_report():
    idx = build([report(sha(i), published=f"2024-01-{i:02d}") for i in range(1, 6)])
    assert {len(v) for v in idx["columns"].values()} == {5}


def test_the_build_is_deterministic_and_does_not_change_its_input():
    rows = [report(sha(i), actors=("G0007",), published=f"2024-01-{i:02d}") for i in range(1, 6)]
    before = copy.deepcopy(rows)
    first = build(rows)
    second = build(list(reversed(rows)))
    assert json.dumps(first) == json.dumps(second)
    assert rows == before


def test_an_empty_build_is_still_a_valid_index():
    idx = build([])
    assert idx["total"] == 0 and idx["columns"]["id"] == []


def test_two_reports_sharing_a_full_id_are_refused():
    with pytest.raises(ValueError, match="more than once"):
        build([report(sha(1)), report(sha(1))])
