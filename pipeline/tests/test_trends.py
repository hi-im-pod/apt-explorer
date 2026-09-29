import pytest

from aptx.build.contract import validator
from aptx.build.trends import WINDOW_START, compute

NOW = "2026-09-30T04:00:00Z"
HEALTH = [{"name": "attack", "last_success": "2026-09-30", "record_count": 10, "stale": False}]


def R(published, actors=(), techniques=(), cves=(), rid=None):
    return {"id": rid or f"attack:{published}-{'-'.join(actors)}", "published": published,
            "actors": list(actors), "techniques": list(techniques), "cves": list(cves)}


def V(cve, added, ransomware=False):
    return {"cve": cve, "kev_date_added": added, "ransomware": ransomware, "vendor": None, "product": None,
            "actors": [], "report_count": 0}


def run(reports=(), documented=None, vulns=(), claims=None, health=HEALTH, **kw):
    return compute(list(reports), documented=documented if documented is not None else {"G0001": []},
                   vulns=list(vulns), first_seen_claims=claims or {}, source_health=health,
                   generated_at=NOW, **kw)


def test_the_output_answers_to_the_published_schema():
    out = run([R("2025-05-01", ["G0001"], ["T1105"])], {"G0001": ["T1105"]}, [V("CVE-2025-0001", "2025-02-03")])
    assert list(validator("trends").iter_errors(out)) == []
    assert out["generated_at"] == NOW
    assert out["window_start"] == WINDOW_START == "2024-01-01"
    assert out["source_health"] == HEALTH
    assert set(out["notes"]) == {"reporting_activity", "new_actors", "kev_monthly", "kev_actor_links",
                                 "reported_vs_documented", "source_health"}


# reporting_activity

def test_reports_before_the_window_only_feed_the_year_earlier_count():
    out = run([R("2023-05-10", ["G0001"]), R("2023-08-01", ["G0001"]), R("2024-05-02", ["G0001"]),
               R("2024-05-20", ["G0001"])])
    assert out["reporting_activity"] == [
        {"actor": "G0001", "quarter": "2024-Q2", "count": 2, "prev_year_count": 1},
        # No 2024-Q3 report, but the 2023-Q3 one shows the drop, so the row stays.
        {"actor": "G0001", "quarter": "2024-Q3", "count": 0, "prev_year_count": 1},
        # The same goes for the 2024 reports one year on: silence after activity is a finding.
        {"actor": "G0001", "quarter": "2025-Q2", "count": 0, "prev_year_count": 2},
    ]


def test_no_2023_quarter_is_reported_as_current_activity():
    out = run([R("2023-05-10", ["G0001"])])
    assert all(row["quarter"] >= "2024-Q1" for row in out["reporting_activity"])
    assert [r["quarter"] for r in out["reporting_activity"]] == ["2024-Q2"]


def test_undated_and_actorless_reports_never_count():
    out = run([R(None, ["G0001"]), R("2025-01-05", []), R("2025-01-05", ["G0001"])])
    assert out["reporting_activity"] == [
        {"actor": "G0001", "quarter": "2025-Q1", "count": 1, "prev_year_count": 0},
        {"actor": "G0001", "quarter": "2026-Q1", "count": 0, "prev_year_count": 1}]


def test_a_report_counts_for_each_of_its_actors():
    out = run([R("2025-04-01", ["G0001", "G0002"])], {"G0001": [], "G0002": []})
    assert {(r["actor"], r["count"]) for r in out["reporting_activity"] if r["count"]} == {("G0001", 1), ("G0002", 1)}


def test_a_report_dated_after_the_build_is_left_out():
    out = run([R("2026-10-15", ["G0001"]), R("2026-09-30", ["G0001"])])
    assert [(r["quarter"], r["count"]) for r in out["reporting_activity"]] == [("2026-Q3", 1)]


def test_quarters_after_the_build_never_get_a_year_earlier_row():
    out = run([R("2025-11-01", ["G0001"])])
    assert [r["quarter"] for r in out["reporting_activity"]] == ["2025-Q4"]


def test_a_later_window_start_drops_earlier_reports_from_the_counts():
    out = run([R("2024-05-01", ["G0001"]), R("2025-05-01", ["G0001"])], window_start="2025-01-01")
    assert out["window_start"] == "2025-01-01"
    # 2024-Q2 is before the window, so it has no row of its own.
    assert out["reporting_activity"] == [
        {"actor": "G0001", "quarter": "2025-Q2", "count": 1, "prev_year_count": 1},
        {"actor": "G0001", "quarter": "2026-Q2", "count": 0, "prev_year_count": 1}]


def test_rows_are_ordered_by_actor_then_quarter():
    out = run([R("2025-08-01", ["G0002"]), R("2025-02-01", ["G0002"]), R("2025-05-01", ["G0001"])],
              {"G0001": [], "G0002": []})
    assert [(r["actor"], r["quarter"]) for r in out["reporting_activity"] if r["quarter"].startswith("2025")] == [
        ("G0001", "2025-Q2"), ("G0002", "2025-Q1"), ("G0002", "2025-Q3")]
    pairs = [(r["actor"], r["quarter"]) for r in out["reporting_activity"]]
    assert pairs == sorted(pairs)


# new_actors

def test_an_actor_first_seen_within_a_year_is_new_and_one_from_2019_is_not():
    out = run([R("2026-02-11", ["G0001"]), R("2019-03-01", ["G0002"]), R("2026-03-01", ["G0002"])],
              {"G0001": [], "G0002": []})
    assert out["new_actors"] == [{"actor": "G0001", "first_seen": "2026-02-11", "basis": "report"}]


def test_the_cutoff_is_365_days_before_the_build():
    # The build is on 2026-09-30, so the cutoff day is 2025-09-30.
    out = run([R("2025-09-30", ["G0001"]), R("2025-09-29", ["G0002"])], {"G0001": [], "G0002": []})
    assert [n["actor"] for n in out["new_actors"]] == ["G0001"]


def test_an_older_source_date_outweighs_a_recent_report():
    out = run([R("2026-02-11", ["G0001"])], claims={"G0001": [("2004-01-01", "year")]})
    assert out["new_actors"] == []


def test_a_year_only_date_counts_when_the_whole_year_is_in_the_window():
    # 2026 starts after the cutoff. 2025 started before it, so the actor may have
    # appeared before the window, and a year says no more than that.
    out = run(documented={"G0001": [], "G0002": [], "G0003": []},
              claims={"G0001": [("2026-01-01", "year")], "G0002": [("2025-01-01", "year")],
                      "G0003": [("2004-01-01", "year")]})
    assert out["new_actors"] == [{"actor": "G0001", "first_seen": "2026-01-01", "basis": "year"}]


def test_a_full_source_date_keeps_its_source_as_the_basis():
    out = run(claims={"G0001": [("2026-04-01", "attack")]})
    assert out["new_actors"] == [{"actor": "G0001", "first_seen": "2026-04-01", "basis": "attack"}]


def test_an_actor_with_no_date_anywhere_is_not_new():
    assert run(reports=[R(None, ["G0001"])])["new_actors"] == []


def test_only_published_actors_can_be_new():
    out = run([R("2026-02-11", ["G0009"])], {"G0001": []})
    assert out["new_actors"] == []


# kev_monthly

def test_kev_additions_are_counted_per_month_with_ransomware_subtotals():
    out = run(vulns=[V("CVE-2025-0001", "2025-01-05", True), V("CVE-2025-0002", "2025-01-20", False),
                     V("CVE-2025-0003", "2025-01-21", None), V("CVE-2025-0004", "2025-03-02", True)])
    months = {m["month"]: m for m in out["kev_monthly"]}
    assert months["2025-01"] == {"month": "2025-01", "added": 3, "ransomware": 1}
    assert months["2025-03"] == {"month": "2025-03", "added": 1, "ransomware": 1}
    # A month with no additions is a real zero, so the chart has no gap.
    assert months["2025-02"] == {"month": "2025-02", "added": 0, "ransomware": 0}


def test_kev_months_run_from_the_window_to_the_build_month():
    out = run(vulns=[V("CVE-2024-0001", "2024-02-01"), V("CVE-2023-0001", "2023-12-31"),
                     V("CVE-2026-0001", "2026-10-02")])
    months = [m["month"] for m in out["kev_monthly"]]
    assert months[0] == "2024-01" and months[-1] == "2026-09"
    assert len(months) == 33
    assert sum(m["added"] for m in out["kev_monthly"]) == 1


def test_no_kev_data_gives_no_months_rather_than_a_run_of_zeros():
    out = run(vulns=[{**V("CVE-2025-0001", None, None)}])
    assert out["kev_monthly"] == []


# kev_actor_links

def test_a_kev_cve_named_in_a_recent_report_links_to_that_reports_actors():
    out = run([R("2025-05-01", ["G0001"], cves=["CVE-2025-0001"]),
               R("2025-06-01", ["G0002"], cves=["CVE-2025-0001"])],
              {"G0001": [], "G0002": []}, [V("CVE-2025-0001", "2025-01-01")])
    assert out["kev_actor_links"] == [{"cve": "CVE-2025-0001", "actors": ["G0001", "G0002"]}]


def test_kev_links_ignore_old_reports_actorless_reports_and_cves_outside_kev():
    out = run([R("2022-05-01", ["G0001"], cves=["CVE-2022-0001"]),
               R("2025-05-01", [], cves=["CVE-2025-0002"]),
               R("2025-05-01", ["G0001"], cves=["CVE-2025-0003"]),
               R(None, ["G0001"], cves=["CVE-2025-0004"])],
              vulns=[V("CVE-2022-0001", "2022-01-01"), V("CVE-2025-0002", "2025-01-01"),
                     V("CVE-2025-0004", "2025-01-01"), V("CVE-2025-0005", None, None)])
    assert out["kev_actor_links"] == []


# reported_vs_documented

def test_reported_techniques_are_compared_with_what_attack_documents():
    out = run([R("2025-05-01", ["G0001"], ["T1105", "T1190"]), R("2025-06-01", ["G0001"], ["T1105"]),
               R("2022-06-01", ["G0001"], ["T1566"])],
              {"G0001": ["T1105", "T1059", "T1003"]})
    assert out["reported_vs_documented"] == [
        {"actor": "G0001", "reported_only": ["T1190"], "documented_only_count": 2, "overlap": 1}]


def test_an_actor_whose_recent_reports_name_no_technique_is_not_compared():
    out = run([R("2025-05-01", ["G0001"], [])], {"G0001": ["T1105"], "G0002": ["T1059"]})
    assert out["reported_vs_documented"] == []


def test_an_actor_ATTACK_does_not_track_has_nothing_documented():
    out = run([R("2025-05-01", ["glass-heron"], ["T1190"])], {"glass-heron": []})
    assert out["reported_vs_documented"] == [
        {"actor": "glass-heron", "reported_only": ["T1190"], "documented_only_count": 0, "overlap": 0}]


def test_output_is_the_same_for_the_same_input_in_any_order():
    reports = [R("2025-05-01", ["G0002", "G0001"], ["T1105", "T1059"], ["CVE-2025-0001"]),
               R("2025-02-01", ["G0001"], ["T1190"])]
    documented = {"G0001": ["T1059"], "G0002": []}
    vulns = [V("CVE-2025-0001", "2025-01-01", True)]
    a = run(reports, documented, vulns)
    b = run(list(reversed(reports)), dict(reversed(list(documented.items()))), vulns)
    assert a == b


def test_generated_at_defaults_to_now_in_the_schema_form():
    out = compute([], documented={}, vulns=[], first_seen_claims={}, source_health=[])
    assert list(validator("trends").iter_errors(out)) == []


@pytest.mark.parametrize("bad", ["2026-09-30", "2026-09-30 04:00:00", "yesterday"])
def test_a_generated_at_that_is_not_a_utc_timestamp_is_refused(bad):
    with pytest.raises(ValueError, match="generated_at"):
        compute([], documented={}, vulns=[], first_seen_claims={}, source_health=[], generated_at=bad)
