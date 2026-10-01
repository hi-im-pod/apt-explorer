import json
from dataclasses import replace

import pytest

from aptx.build import slugs, trends, write
from aptx.build.assemble import BuildFacts, assemble
from aptx.build.notice import SOURCE_ORDER, render_notice, source_attribution
from aptx.core.models import (ActorRecord, CampaignRecord, ReportRecord, SoftwareRecord, SourceBundle,
                              VulnRecord)
from aptx.resolve.registry import resolve

NOW = "2026-09-30T04:00:00Z"
SNAP = "2026-09-28"
POLICIES = {"attack": "full", "misp": "full", "etda": "derived-only", "malpedia": "derived-only",
            "orkl": "link-only", "kev": "full", "dfir": "link-only", "paper": "full", "microsoft": "full",
            "epss": "full", "talos": "link-only", "eset": "link-only", "microsoftblog": "link-only"}
TECHNIQUES = frozenset({"T1059", "T1105", "T1190", "T1566", "T1566.002", "T1505.003", "T1090.003"})
FACTS = BuildFacts(copyright_year="2026", valid_techniques=TECHNIQUES,
                   snapshot_dates={key: SNAP for key in SOURCE_ORDER})
MIRROR = "https://github.com/CyberMonitor/APT_CyberCriminal_Campagin_Collections/raw/master/2019/x.pdf"
BOX = "https://app.box.com/s/abc123"


def A(source, sid, name, **kw):
    return ActorRecord(source=source, source_id=sid, name=name, retrieved_at=SNAP, **kw)


def R(source, sid, title="A report", url=None, published=None, basis=None, **kw):
    if basis is None:
        basis = "unknown" if published is None else {"orkl": "malpedia-library", "dfir": "publisher",
                                                     "paper": "paper"}[source]
    return ReportRecord(source=source, source_id=sid, title=title, published=published, date_basis=basis,
                        url=url, retrieved_at=SNAP, **kw)


def C(sid, name, actors=(), **kw):
    return CampaignRecord(source="attack", source_id=sid, name=name, actor_refs=list(actors),
                          retrieved_at=SNAP, **kw)


def V(cve, added=None, ransomware=None, vendor=None, product=None, epss=None, percentile=None):
    return VulnRecord(cve=cve, kev_date_added=added, ransomware=ransomware, vendor=vendor, product=product,
                      epss=epss, epss_percentile=percentile, retrieved_at=SNAP)


def B(source, **kw):
    return SourceBundle(source=source, **kw)


def run(*bundles, policies=None, facts=None, check=True, **kw):
    """Assemble from in-memory bundles, resolving actors exactly as the CLI does."""
    actors = [a for b in bundles for a in b.actors]
    software = [s for b in bundles for s in b.software]
    policies = {**POLICIES, **(policies or {})}
    # The registry is told which sources may name a page, as the CLI does, or assemble() refuses it.
    registry = resolve(actors, software, shown_sources=slugs.shown_sources(policies), build_date=NOW[:10])
    payload = assemble(list(bundles), registry, policies, generated_at=NOW, facts=facts or FACTS, **kw)
    if check:
        # Every payload a test builds must also be one the writer accepts.
        write.validate(payload)
    return payload


def WORLD(**extra):
    """ATT&CK, MISP and ETDA agree on APT28, and one glass-heron only MISP knows."""
    attack = B("attack",
               actors=[A("attack", "G0007", "APT28", aliases=["Fancy Bear", "Sofacy"], malware=["X-Agent"],
                         techniques=["T1059", "T1566"])],
               campaigns=[C("C0001", "Operation Blue", ["G0007", "G9999"], first_seen="2019-09-01",
                            last_seen="2020-01-01", techniques=["T1059"])])
    misp = B("misp", actors=[
        A("misp", "m1", "Fancy Bear", aliases=["APT28", "Sofacy", "G0007"], origin=["RU"],
          sponsor=["Russian Federation"], motivation=["Espionage"],
          targets_countries=["Ukraine", "USA"], targets_sectors=["Government"]),
        A("misp", "m2", "Glass Heron", aliases=["Heron Cluster 7"], motivation=["Espionage"])])
    etda = B("etda", actors=[A("etda", "e1", "APT 28", origin=["Russia"], first_seen=["2004"],
                               motivation=["Information theft and espionage"])])
    bundles = {"attack": attack, "misp": misp, "etda": etda}
    bundles.update(extra)
    return list(bundles.values())


def data(payload, rel):
    return payload[rel]


def actor_files(payload):
    return {rel: v for rel, v in payload.items() if rel.startswith("actors/") and rel != "actors/index.json"}


def all_report_rows(payload):
    return [r for rel, rows in payload.items() if rel.startswith("reports/") and rel != "reports/index.json"
            for r in rows]


def report_by_title(payload, title):
    rows = [r for r in all_report_rows(payload) if r["title"] == title]
    assert len(rows) == 1, f"{title!r} appears {len(rows)} times"
    return rows[0]


def text(value):
    return json.dumps(value, ensure_ascii=False)


# The output as a whole

def test_the_payload_is_the_files_of_data_and_the_writer_accepts_it():
    payload = run(*WORLD())
    assert {"actors/index.json", "actors/G0007.json", "actors/glass-heron.json", "reports/undated.json",
            "campaigns.json", "vulns.json", "sources.json", "resolution.json", "trends.json", "build.json",
            "NOTICE.md"} <= set(payload)
    assert payload["NOTICE.md"] == render_notice("2026")


def test_an_empty_build_is_still_a_complete_tree():
    payload = run(*[B(key) for key in SOURCE_ORDER])
    assert payload["actors/index.json"] == [] and payload["reports/undated.json"] == []
    assert payload["build.json"]["report_years"] == []
    assert payload["build.json"]["report_count"] == 0
    assert len(payload["sources.json"]) == len(SOURCE_ORDER)


def test_bundles_may_arrive_as_a_dict_or_a_list_in_any_order():
    world = WORLD()
    as_dict = {b.source: b for b in reversed(world)}
    payload = assemble(as_dict, resolve([a for b in world for a in b.actors], [], shown_sources=slugs.shown_sources(POLICIES),
                               build_date=NOW[:10]),
                       POLICIES, generated_at=NOW, facts=FACTS)
    assert payload == run(*world)


def test_the_same_input_gives_the_same_payload_in_any_order():
    a = run(*WORLD())
    b = run(*reversed(WORLD()))
    assert a == b


def test_the_payload_is_json_only_and_the_notice():
    payload = run(*WORLD())
    for rel, value in payload.items():
        if rel != "NOTICE.md":
            json.dumps(value, allow_nan=False)


# Publish policy

def test_link_only_source_values_never_reach_an_actor_file():
    orkl = B("orkl", actors=[A("orkl", "o1", "Fancy Bear", aliases=["OrklOnlyAlias"], origin=["CN"],
                               targets_sectors=["OrklSector"], malware=["OrklMalware"],
                               targets_countries=["Japan"], sponsor=["OrklSponsor"],
                               motivation=["OrklMotive"], first_seen=["2026-05-01"])])
    payload = run(*WORLD(), orkl)
    everything = text({k: v for k, v in payload.items() if k != "NOTICE.md"})
    for leaked in ("OrklOnlyAlias", "OrklSector", "OrklMalware", "OrklSponsor", "OrklMotive"):
        assert leaked not in everything
    assert "orkl" not in payload["actors/G0007.json"].keys()
    index = {e["id"]: e for e in payload["actors/index.json"]}
    assert "orkl" not in index["G0007"]["sources"]
    assert payload["actors/G0007.json"]["origin"] == [{"value": "RU", "source": "misp"},
                                                       {"value": "RU", "source": "etda"}]
    assert payload["trends.json"]["new_actors"] == []


def test_a_link_only_source_still_counts_as_merge_evidence():
    without = run(*WORLD())
    orkl = B("orkl", actors=[A("orkl", "o1", "Fancy Bear")])
    with_orkl = run(*WORLD(), orkl)
    assert with_orkl["actors/G0007.json"]["evidence_count"] > without["actors/G0007.json"]["evidence_count"]


def test_etda_drift_hides_every_etda_value_but_still_counts_as_merge_evidence():
    etda = B("etda", actors=[A("etda", "e1", "APT 28", aliases=["EtdaOnlyAlias"], origin=["China"],
                               motivation=["EtdaMotive"], targets_sectors=["EtdaSector"],
                               targets_countries=["Japan"], first_seen=["2026"], malware=["EtdaMalware"])])
    shown = run(*WORLD(etda=etda))
    hidden = run(*WORLD(etda=etda), policies={"etda": "evidence-only"})
    blob = text({k: v for k, v in hidden.items() if k != "NOTICE.md"})
    for leaked in ("EtdaOnlyAlias", "EtdaMotive", "EtdaSector", "EtdaMalware"):
        assert leaked not in blob
        assert leaked in text(shown)
    # As a source of a fact, "etda" appears nowhere. Its own health rows are the only mention.
    facts_only = {k: v for k, v in hidden["actors/G0007.json"].items() if k != "evidence_count"}
    assert '"etda"' not in text(facts_only)
    actor = hidden["actors/G0007.json"]
    assert {c["source"] for c in actor["origin"]} == {"misp"}
    assert actor["conflicts"] == []
    assert actor["evidence_count"] == shown["actors/G0007.json"]["evidence_count"] > 0
    assert hidden["trends.json"]["new_actors"] == []
    assert [s for s in hidden["sources.json"] if s["name"] == "etda"][0]["publish"] == "evidence-only"


def test_an_actor_only_an_evidence_only_source_knows_is_not_published():
    etda = B("etda", actors=[A("etda", "e2", "Hidden Panda", origin=["China"])])
    payload = run(*WORLD(etda=etda), policies={"etda": "evidence-only"})
    assert "actors/hidden-panda.json" not in payload
    assert all(e["id"] != "hidden-panda" for e in payload["actors/index.json"])
    # The registry still counts it, because merge statistics describe the registry.
    assert payload["resolution.json"]["stats"]["actor_count"] >= 3
    assert "Hidden Panda" not in text({k: v for k, v in payload.items() if k != "NOTICE.md"})


def test_the_display_name_never_comes_from_a_hidden_source():
    # Two evidence-only ETDA cards outvote the one MISP record on the most common name.
    etda = B("etda", actors=[A("etda", "e1", "Secret Name", aliases=["Shared Key"]),
                             A("etda", "e2", "Secret Name", aliases=["Shared Key"])])
    misp = B("misp", actors=[A("misp", "m1", "Public Name", aliases=["Shared Key"])])
    payload = run(etda, misp, policies={"etda": "evidence-only"})
    assert [e["name"] for e in payload["actors/index.json"]] == ["Public Name"]
    assert "Secret Name" not in text({k: v for k, v in payload.items() if k != "NOTICE.md"})


def test_reports_from_an_evidence_only_source_are_not_published():
    orkl = B("orkl", reports=[R("orkl", "1", "Hidden report", "https://ex.org/a", "2025-01-01")])
    payload = run(*WORLD(orkl=orkl), policies={"orkl": "evidence-only"})
    assert all_report_rows(payload) == []
    assert [s for s in payload["sources.json"] if s["name"] == "orkl"][0]["record_count"] == 1


def test_a_source_with_no_policy_is_refused():
    policies = dict(POLICIES)
    del policies["etda"]
    with pytest.raises(ValueError, match="etda"):
        assemble(WORLD(), resolve([], []), policies, generated_at=NOW, facts=FACTS)


def test_an_unknown_policy_value_is_refused():
    with pytest.raises(ValueError, match="everything"):
        assemble(WORLD(), resolve([], []), {**POLICIES, "misp": "everything"}, generated_at=NOW, facts=FACTS)


def test_a_bundle_from_a_source_the_contract_does_not_know_is_refused():
    with pytest.raises(ValueError, match="mystery"):
        assemble([B("mystery")], resolve([], []), POLICIES, generated_at=NOW, facts=FACTS)


def test_a_build_without_a_copyright_year_is_refused():
    with pytest.raises(ValueError, match="copyright"):
        assemble(WORLD(), resolve([], []), POLICIES, generated_at=NOW,
                 facts=replace(FACTS, copyright_year=None))


@pytest.mark.parametrize("bad", ["2026-09-30", "now"])
def test_a_generated_at_that_is_not_a_utc_timestamp_is_refused(bad):
    with pytest.raises(ValueError, match="generated_at"):
        assemble(WORLD(), resolve([], []), POLICIES, generated_at=bad, facts=FACTS)


def test_generated_at_defaults_to_now():
    payload = assemble(WORLD(), resolve([a for b in WORLD() for a in b.actors], []), POLICIES, facts=FACTS)
    write.validate(payload)


# Actor pages

def test_an_actor_page_names_only_published_facts_with_their_sources():
    actor = run(*WORLD())["actors/G0007.json"]
    assert actor["id"] == "G0007" and actor["name"] == "APT28"
    aliases = {a["value"]: a["sources"] for a in actor["aliases"]}
    assert aliases["APT28"] == ["attack", "misp", "etda"] or set(aliases["APT28"]) >= {"attack", "misp"}
    assert aliases["Fancy Bear"] == ["attack", "misp"]
    assert actor["aliases"][0]["value"] == "APT28"
    assert actor["sponsor"] == [{"value": "Russian Federation", "source": "misp"}]
    assert actor["malware"] == [{"name": "X-Agent", "source": "attack"}]
    assert actor["techniques_documented"] == ["T1059", "T1566"]
    assert actor["evidence_count"] > 0


def test_id_shaped_aliases_are_never_published():
    payload = run(*WORLD())
    assert "G0007" not in [a["value"] for a in payload["actors/G0007.json"]["aliases"]]
    entry = [e for e in payload["actors/index.json"] if e["id"] == "G0007"][0]
    assert "G0007" not in entry["aliases"]
    assert entry["aliases"][0] == "APT28"


def test_the_index_lists_the_same_aliases_as_the_actor_page():
    payload = run(*WORLD())
    entry = [e for e in payload["actors/index.json"] if e["id"] == "G0007"][0]
    assert entry["aliases"] == [a["value"] for a in payload["actors/G0007.json"]["aliases"]]
    assert entry["sources"] == ["attack", "misp", "etda"]
    assert entry["origin"] == ["RU"]


def test_unidentified_malpedia_families_are_not_listed_as_actor_malware():
    malpedia = B("malpedia", actors=[A("malpedia", "apt28", "APT28", malware=["unidentified 042", "Unidentified 7",
                                                                              "Sofacy Loader"])])
    payload = run(*WORLD(malpedia=malpedia))
    assert {"name": "Sofacy Loader", "source": "malpedia"} in payload["actors/G0007.json"]["malware"]
    assert "nidentified" not in text(payload["actors/G0007.json"]["malware"])


def test_sector_values_over_80_characters_are_dropped():
    long = "S" * 81
    misp = B("misp", actors=[A("misp", "m1", "Fancy Bear", aliases=["APT28"],
                               targets_sectors=["Government", long, "T" * 80])])
    payload = run(WORLD()[0], misp)
    sectors = [s["value"] for s in payload["actors/G0007.json"]["claimed_targets"]["sectors"]]
    assert sectors == ["Government", "T" * 80]


def test_target_countries_are_countries_and_use_one_spelling():
    misp = B("misp", actors=[A("misp", "m1", "Fancy Bear", aliases=["APT28"], targets_countries=[
        "USA", "United States", "Iran (Islamic Republic of)", "Korea (Republic of)", "Worldwide", "[Unknown]",
        "Southeast Asia", "World Anti-Doping Agency", "U.S. satellite and aerospace sector"])])
    payload = run(WORLD()[0], misp)
    countries = payload["actors/G0007.json"]["claimed_targets"]["countries"]
    assert [c["value"] for c in countries] == ["United States", "Iran", "South Korea"]
    assert {c["source"] for c in countries} == {"misp"}


# Country conflicts

def _origin_run(*origins):
    records = [A("attack", "G0007", "APT28")]
    bundles = [B("attack", actors=records)]
    for source, value in origins:
        bundles.append(B(source, actors=[A(source, f"{source}1", "APT28", origin=[value])]))
    return run(*bundles)["actors/G0007.json"]


def test_russia_and_ru_are_not_a_conflict():
    actor = _origin_run(("etda", "Russia"), ("misp", "RU"))
    assert actor["conflicts"] == []
    assert sorted(o["value"] for o in actor["origin"]) == ["RU", "RU"]


def test_ru_against_cn_is_a_conflict_and_every_side_is_shown():
    actor = _origin_run(("misp", "RU"), ("malpedia", "cn"))
    assert actor["conflicts"] == [{"field": "origin", "values": [{"value": "RU", "source": "misp"},
                                                                {"value": "CN", "source": "malpedia"}]}]


def test_a_source_listing_two_origins_does_not_conflict_with_itself():
    records = [A("attack", "G0007", "APT28"), A("misp", "m1", "APT28", origin=["RU", "BY"])]
    actor = run(B("attack", actors=records[:1]), B("misp", actors=records[1:]))["actors/G0007.json"]
    assert actor["conflicts"] == []


def test_sources_that_share_an_origin_do_not_conflict():
    records = [A("misp", "m1", "APT28", origin=["RU"]), A("etda", "e1", "APT28", origin=["Russia", "Belarus"])]
    payload = run(B("misp", actors=records[:1]), B("etda", actors=records[1:]))
    assert payload["actors/apt28.json"]["conflicts"] == []


def test_north_and_south_korea_are_told_apart():
    actor = _origin_run(("etda", "North Korea"), ("misp", "Korea (Republic of)"))
    assert [o["value"] for o in actor["origin"]] == ["KR", "KP"]
    assert actor["conflicts"][0]["field"] == "origin"


def test_sponsor_conflicts_compare_countries_not_wording():
    misp = A("misp", "m1", "APT28", sponsor=["Iran (Islamic Republic of)"])
    etda = A("etda", "e1", "APT28", sponsor=["Iran"])
    actor = run(B("misp", actors=[misp]), B("etda", actors=[etda]))["actors/apt28.json"]
    assert actor["conflicts"] == []
    other = A("etda", "e1", "APT28", sponsor=["China"])
    actor = run(B("misp", actors=[misp]), B("etda", actors=[other]))["actors/apt28.json"]
    assert [c["field"] for c in actor["conflicts"]] == ["sponsor"]


def test_motivation_wording_that_contains_the_other_is_not_a_conflict():
    actor = run(*WORLD())["actors/G0007.json"]
    assert {m["value"] for m in actor["motivation"]} == {"Espionage", "Information theft and espionage"}
    assert actor["conflicts"] == []
    misp = A("misp", "m1", "APT28", motivation=["Espionage"])
    etda = A("etda", "e1", "APT28", motivation=["Financial crime"])
    actor = run(B("misp", actors=[misp]), B("etda", actors=[etda]))["actors/apt28.json"]
    assert [c["field"] for c in actor["conflicts"]] == ["motivation"]


def test_origin_wording_that_is_not_a_country_is_dropped():
    actor = _origin_run(("etda", "Southeast Asia"), ("misp", "RU"))
    assert [o["value"] for o in actor["origin"]] == ["RU"]


# Reports: dates and shards

def test_a_report_dated_2024_05_01_lands_in_the_2024_shard():
    orkl = B("orkl", reports=[R("orkl", "1", "May report", "https://ex.org/may", "2024-05-01")])
    payload = run(*WORLD(orkl=orkl))
    assert [r["title"] for r in payload["reports/2024.json"]] == ["May report"]
    assert payload["build.json"]["report_years"] == [2024]
    row = payload["reports/2024.json"][0]
    assert (row["published"], row["date_basis"]) == ("2024-05-01", "malpedia-library")


def test_an_undated_report_is_in_the_undated_shard_and_out_of_trends():
    orkl = B("orkl", reports=[R("orkl", "1", "No date", "https://ex.org/a")])
    misp_links = {"ex.org/a": ["APT28"]}
    payload = run(*WORLD(orkl=orkl), facts=replace(FACTS, malpedia_report_links=misp_links))
    row = payload["reports/undated.json"][0]
    assert (row["title"], row["published"], row["date_basis"]) == ("No date", None, "unknown")
    assert row["actors"] == ["G0007"]
    assert payload["build.json"]["report_years"] == []
    assert payload["actors/G0007.json"]["reports"] == [row["id"]]
    assert payload["actors/G0007.json"]["timeline"] == []
    assert payload["trends.json"]["reporting_activity"] == []
    entry = [e for e in payload["actors/index.json"] if e["id"] == "G0007"][0]
    assert (entry["report_count"], entry["last_reported"]) == (1, None)


def _linked(*reports, links=None, **kw):
    urls = {}
    for r in reports:
        urls.setdefault(r.url.lower().split("//")[-1], ["APT28"])
    orkl = B("orkl", reports=list(reports))
    return run(*WORLD(orkl=orkl), facts=replace(FACTS, malpedia_report_links=links or urls), **kw)


def test_a_report_before_the_window_is_out_of_reporting_activity_but_supplies_prev_year_count():
    payload = _linked(R("orkl", "1", "Old", "https://ex.org/old", "2023-08-10"),
                      R("orkl", "2", "New", "https://ex.org/new", "2024-08-02"))
    trends = payload["trends.json"]
    rows = trends["reporting_activity"]
    assert trends["window_start"] == "2024-07-01"
    assert all(r["quarter"] >= "2024-Q3" for r in rows)
    assert {"actor": "G0007", "quarter": "2024-Q3", "count": 1, "prev_year_count": 1} in rows
    assert [r["title"] for r in payload["reports/2023.json"]] == ["Old"]


def test_a_future_dated_report_is_treated_as_undated():
    payload = _linked(R("orkl", "1", "Later", "https://ex.org/later", "2027-01-01"))
    row = payload["reports/undated.json"][0]
    assert (row["published"], row["date_basis"]) == (None, "unknown")


def test_the_best_dated_record_of_a_merged_report_gives_the_date():
    orkl = R("orkl", "1", "Merged", "https://ex.org/m", "2025-03-01", basis="orkl-ingest")
    dfir = R("dfir", "m", "Merged", "https://EX.org/m/", "2025-02-20", basis="publisher")
    payload = run(*WORLD(orkl=B("orkl", reports=[orkl]), dfir=B("dfir", reports=[dfir])))
    row = report_by_title(payload, "Merged")
    assert (row["published"], row["date_basis"]) == ("2025-02-20", "publisher")
    assert row["sources"] == ["orkl", "dfir"]


def test_the_paper_is_a_historical_layer_that_does_not_feed_trends():
    paper = B("paper", reports=[R("paper", "a.pdf", "Paper report", "https://ex.org/p", "2025-05-01",
                                  actor_names=["APT28"])])
    payload = run(*WORLD(paper=paper))
    assert payload["actors/G0007.json"]["reports"] == [report_by_title(payload, "Paper report")["id"]]
    assert payload["actors/G0007.json"]["timeline"] == [{"quarter": "2025-Q2", "count": 1}]
    assert payload["trends.json"]["reporting_activity"] == []
    assert payload["trends.json"]["reported_vs_documented"] == []
    assert payload["actors/G0007.json"]["techniques_reported"] == []


# Reports: identity, links and mirrors

def test_a_report_id_is_its_sha1_or_source_and_source_id():
    orkl = B("orkl", reports=[R("orkl", "77", "With hash", "https://ex.org/1", "2025-01-01", sha1="a" * 40),
                              R("orkl", "78", "No hash", "https://ex.org/2", "2025-01-02")])
    paper = B("paper", reports=[R("paper", "My report.pdf", "Paper only", "https://ex.org/3", "2019-01-01")])
    payload = run(*WORLD(orkl=orkl, paper=paper))
    assert report_by_title(payload, "With hash")["id"] == "a" * 40
    assert report_by_title(payload, "No hash")["id"] == "orkl:78"
    assert report_by_title(payload, "Paper only")["id"] == "paper:My%20report.pdf"


def test_reports_that_share_a_url_or_a_hash_are_one_report():
    orkl = B("orkl", reports=[R("orkl", "1", "By hash", "https://a.example/x", "2025-01-01", sha1="b" * 40),
                              R("orkl", "2", "By hash again", "https://b.example/y", "2025-01-01",
                                sha1="b" * 40)])
    dfir = B("dfir", reports=[R("dfir", "z", "By url", "http://www.thedfirreport.com/z/", "2025-04-01")])
    orkl2 = B("orkl", reports=orkl.reports + [R("orkl", "3", "By url too", "https://thedfirreport.com/z",
                                               "2025-04-01")])
    payload = run(*WORLD(orkl=orkl2, dfir=dfir))
    assert len(all_report_rows(payload)) == 2


def test_an_actor_named_by_malpedia_links_the_report_by_normalized_url():
    orkl = B("orkl", reports=[R("orkl", "1", "Linked", "https://www.Example.org/a/", "2025-06-01")])
    facts = replace(FACTS, malpedia_report_links={"example.org/a": ["Sofacy", "Some Unknown Crew"]})
    payload = run(*WORLD(orkl=orkl), facts=facts)
    row = report_by_title(payload, "Linked")
    assert row["actors"] == ["G0007"]
    assert row["actor_names_unresolved"] == ["Some Unknown Crew"]


def test_malpedia_links_are_ignored_when_malpedia_is_evidence_only():
    orkl = B("orkl", reports=[R("orkl", "1", "Linked", "https://example.org/a", "2025-06-01")])
    facts = replace(FACTS, malpedia_report_links={"example.org/a": ["Sofacy", "Some Unknown Crew"]})
    payload = run(*WORLD(orkl=orkl), facts=facts, policies={"malpedia": "evidence-only"})
    row = report_by_title(payload, "Linked")
    assert row["actors"] == [] and row["actor_names_unresolved"] == []


def test_attack_group_references_link_reports_to_the_group():
    orkl = B("orkl", reports=[R("orkl", "1", "Cited", "http://example.org/cited", "2025-06-01")])
    facts = replace(FACTS, group_reference_urls={"G0007": ["https://www.example.org/cited/"],
                                                 "G9999": ["https://example.org/cited"]})
    payload = run(*WORLD(orkl=orkl), facts=facts)
    assert report_by_title(payload, "Cited")["actors"] == ["G0007"]


def test_the_papers_own_actor_names_link_and_the_rest_stay_unresolved():
    paper = B("paper", reports=[R("paper", "a.pdf", "Paper report", "https://ex.org/p", "2019-05-01",
                                  actor_names=["Sofacy", "Mystery Bear", "Mimikatz"])])
    world = WORLD(paper=paper)
    world[0] = world[0].model_copy(update={"software": [SoftwareRecord(
        source="attack", source_id="S0002", name="Mimikatz", kind="tool", retrieved_at=SNAP)]})
    payload = run(*world)
    row = report_by_title(payload, "Paper report")
    assert row["actors"] == ["G0007"]
    assert row["actor_names_unresolved"] == ["Mimikatz", "Mystery Bear"]
    names = {n["name"]: n for n in payload["resolution.json"]["unresolved_names"]}
    assert names["Mimikatz"] == {"name": "Mimikatz", "count": 1, "typed_as": "tool"}
    assert names["Mystery Bear"]["typed_as"] is None


def test_a_report_tagged_only_by_orkl_has_no_actors_and_no_unresolved_names():
    # The connector already empties actor_names for a link-only ORKL. A record that still carries
    # tags, as it would if the policy were widened, must not attach or display them either.
    orkl = B("orkl", reports=[R("orkl", "1", "Tagged", "https://ex.org/t", "2025-06-01",
                                actor_names=["APT28", "Unknown Tag"])])
    payload = run(*WORLD(orkl=orkl))
    row = report_by_title(payload, "Tagged")
    assert row["actors"] == [] and row["actor_names_unresolved"] == []
    assert "Unknown Tag" not in text(payload["resolution.json"])


def test_orkl_tags_do_not_attach_a_report_even_under_a_full_policy():
    orkl = B("orkl", reports=[R("orkl", "1", "Tagged", "https://ex.org/t", "2025-06-01", actor_names=["APT28"])])
    payload = run(*WORLD(orkl=orkl), policies={"orkl": "full"})
    assert report_by_title(payload, "Tagged")["actors"] == []


def test_dfir_names_never_attach_a_report():
    dfir = B("dfir", reports=[R("dfir", "z", "Dfir", "https://thedfirreport.com/z", "2025-06-01",
                                actor_names=["APT28"])])
    assert report_by_title(run(*WORLD(dfir=dfir)), "Dfir")["actors"] == []


def test_a_report_naming_an_actor_that_is_not_published_drops_the_link_without_listing_the_name():
    etda = B("etda", actors=[A("etda", "e2", "Hidden Panda")])
    paper = B("paper", reports=[R("paper", "a.pdf", "Paper report", "https://ex.org/p", "2019-05-01",
                                  actor_names=["Hidden Panda"])])
    payload = run(*WORLD(etda=etda, paper=paper), policies={"etda": "evidence-only"})
    row = report_by_title(payload, "Paper report")
    assert row["actors"] == [] and row["actor_names_unresolved"] == []


def test_the_original_url_is_the_publisher_and_the_mirror_becomes_the_archive():
    orkl = B("orkl", reports=[R("orkl", "1", "Mirrored", MIRROR, "2019-05-01", sha1="c" * 40),
                              R("orkl", "2", "Mirrored", "https://vendor.example/blog/x", "2019-05-01",
                                sha1="c" * 40)])
    row = report_by_title(run(*WORLD(orkl=orkl)), "Mirrored")
    assert row["url"] == "https://vendor.example/blog/x"
    assert row["archive_url"] == MIRROR


def test_a_source_archive_is_kept_over_a_mirror():
    orkl = B("orkl", reports=[R("orkl", "1", "Both", MIRROR, "2019-05-01", sha1="c" * 40,
                                archive_url="https://orkl.eu/x.pdf"),
                              R("orkl", "2", "Both", "https://vendor.example/blog/x", "2019-05-01",
                                sha1="c" * 40)])
    row = report_by_title(run(*WORLD(orkl=orkl)), "Both")
    assert (row["url"], row["archive_url"]) == ("https://vendor.example/blog/x", "https://orkl.eu/x.pdf")


@pytest.mark.parametrize("mirror", [MIRROR, BOX, "https://raw.githubusercontent.com/CyberMonitor/APT/x.pdf"])
def test_a_mirror_that_is_the_only_url_is_published_as_the_url(mirror):
    paper = B("paper", reports=[R("paper", "a.pdf", "Only mirror", mirror, "2019-05-01")])
    row = report_by_title(run(*WORLD(paper=paper)), "Only mirror")
    assert row["url"] == mirror
    assert row["archive_url"] is None


def test_a_github_url_that_is_not_the_mirror_is_a_publisher_url():
    paper = B("paper", reports=[R("paper", "a.pdf", "Own repo", "https://github.com/vendor/reports/blob/x.md",
                                  "2019-05-01"),
                                R("paper", "b.pdf", "Own repo", "https://github.com/vendor/reports/blob/x.md",
                                  "2019-05-01")])
    row = report_by_title(run(*WORLD(paper=paper)), "Own repo")
    assert row["url"] == "https://github.com/vendor/reports/blob/x.md" and row["archive_url"] is None


def test_url_ok_comes_from_the_link_check_by_normalized_url():
    orkl = B("orkl", reports=[R("orkl", "1", "Alive", "https://www.ex.org/a/", "2025-06-01"),
                              R("orkl", "2", "Dead", "https://ex.org/b", "2025-06-02"),
                              R("orkl", "3", "Unchecked", "https://ex.org/c", "2025-06-03"),
                              R("orkl", "4", "No link", None, "2025-06-04")])
    payload = run(*WORLD(orkl=orkl), link_status={"https://ex.org/a": True, "ex.org/b": False})
    assert [report_by_title(payload, t)["url_ok"] for t in ("Alive", "Dead", "Unchecked", "No link")] == [
        True, False, None, None]


def test_technique_ids_outside_attack_are_dropped_from_reports():
    paper = B("paper", reports=[R("paper", "a.pdf", "Techniques", "https://ex.org/p", "2019-05-01",
                                  techniques=["T1059", "T9999", "T1566.002", "T1566.999"],
                                  cves=["cve-2021-44228", "CVE-2021-44228", "not-a-cve"])])
    row = report_by_title(run(*WORLD(paper=paper)), "Techniques")
    assert row["techniques"] == ["T1059", "T1566.002"]
    assert row["cves"] == ["CVE-2021-44228"]


def test_report_text_is_tidied_and_a_bad_url_is_dropped():
    orkl = B("orkl", reports=[ReportRecord(source="orkl", source_id="1", title="  Two\n lines  ",
                                           date_basis="unknown", url="ftp://ex.org/a", organisation=" \n ",
                                           retrieved_at=SNAP)])
    row = all_report_rows(run(*WORLD(orkl=orkl)))[0]
    assert (row["title"], row["url"], row["organisation"], row["url_ok"]) == ("Two lines", None, None, None)


# Actor pages: reports, timeline, techniques, CVEs

def _busy_world(policies=None, **extra):
    orkl = B("orkl", reports=[
        R("orkl", "1", "Q1 2024", "https://ex.org/1", "2024-02-10", techniques=["T1059", "T1190"],
          cves=["CVE-2024-0001"]),
        R("orkl", "2", "Q1 2024 too", "https://ex.org/2", "2024-03-10", techniques=["T1059"]),
        R("orkl", "3", "Q3 2025", "https://ex.org/3", "2025-08-01", techniques=["T1105"],
          cves=["CVE-2024-0001", "CVE-2025-0002"]),
        R("orkl", "4", "Undated", "https://ex.org/4"),
        R("orkl", "5", "Old", "https://ex.org/5", "2022-01-01", techniques=["T1566"])])
    links = {f"ex.org/{n}": ["APT28"] for n in range(1, 6)}
    kev = B("kev", vulns=[V("CVE-2024-0001", "2024-02-01", True, "Vendor", "Product"),
                          V("CVE-2023-0009", "2023-05-01", False, "Other", "Thing")])
    return run(*WORLD(orkl=orkl, kev=kev, **extra), policies=policies,
               facts=replace(FACTS, malpedia_report_links=links))


def test_an_actor_page_lists_reports_newest_first_with_undated_last():
    payload = _busy_world()
    ids = {t: report_by_title(payload, t)["id"] for t in ("Q1 2024", "Q1 2024 too", "Q3 2025", "Undated", "Old")}
    assert payload["actors/G0007.json"]["reports"] == [ids["Q3 2025"], ids["Q1 2024 too"], ids["Q1 2024"],
                                                       ids["Old"], ids["Undated"]]
    entry = [e for e in payload["actors/index.json"] if e["id"] == "G0007"][0]
    assert (entry["report_count"], entry["last_reported"]) == (5, "2025-08-01")


def test_the_timeline_counts_dated_reports_per_quarter_oldest_first():
    assert _busy_world()["actors/G0007.json"]["timeline"] == [
        {"quarter": "2022-Q1", "count": 1}, {"quarter": "2024-Q1", "count": 2}, {"quarter": "2025-Q3", "count": 1}]


def test_reported_techniques_count_only_reports_inside_the_rolling_window():
    # The two Q1 2024 reports name T1059 and T1190 but fall before the window, which starts 2024-07-01.
    assert _busy_world()["actors/G0007.json"]["techniques_reported"] == [{"id": "T1105", "count": 1}]


def test_reported_techniques_add_up_across_reports_inside_the_window():
    payload = _linked(R("orkl", "1", "One", "https://ex.org/one", "2025-02-10", techniques=["T1059", "T1190"]),
                      R("orkl", "2", "Two", "https://ex.org/two", "2025-03-10", techniques=["T1059"]),
                      R("orkl", "3", "Before", "https://ex.org/before", "2024-06-30", techniques=["T1105"]))
    assert payload["actors/G0007.json"]["techniques_reported"] == [
        {"id": "T1059", "count": 2}, {"id": "T1190", "count": 1}]


def test_an_actor_page_lists_report_cves_with_their_kev_status():
    assert _busy_world()["actors/G0007.json"]["cves"] == [
        {"cve": "CVE-2024-0001", "kev": True, "ransomware": True},
        {"cve": "CVE-2025-0002", "kev": False, "ransomware": None}]


# Vulnerabilities

def test_vulns_hold_every_kev_cve_and_every_cve_named_in_a_published_report():
    vulns = {v["cve"]: v for v in _busy_world()["vulns.json"]}
    assert set(vulns) == {"CVE-2023-0009", "CVE-2024-0001", "CVE-2025-0002"}
    assert vulns["CVE-2024-0001"] == {"cve": "CVE-2024-0001", "kev_date_added": "2024-02-01", "ransomware": True,
                                      "vendor": "Vendor", "product": "Product", "actors": ["G0007"],
                                      "report_count": 2, "epss": None, "epss_percentile": None}
    assert vulns["CVE-2023-0009"]["actors"] == [] and vulns["CVE-2023-0009"]["report_count"] == 0
    assert vulns["CVE-2025-0002"] == {"cve": "CVE-2025-0002", "kev_date_added": None, "ransomware": None,
                                      "vendor": None, "product": None, "actors": ["G0007"], "report_count": 1,
                                      "epss": None, "epss_percentile": None}
    assert [v["cve"] for v in _busy_world()["vulns.json"]] == sorted(vulns)


def test_epss_scores_attach_to_cves_the_page_already_lists_and_never_add_one():
    payload = _busy_world(epss=B("epss", vulns=[V("CVE-2024-0001", epss=0.5, percentile=0.9),
                                                V("CVE-2023-0009", epss=0.01, percentile=0.2),
                                                V("CVE-2020-9999", epss=0.99, percentile=1.0)]))
    vulns = {v["cve"]: v for v in payload["vulns.json"]}
    assert set(vulns) == {"CVE-2023-0009", "CVE-2024-0001", "CVE-2025-0002"}
    assert (vulns["CVE-2024-0001"]["epss"], vulns["CVE-2024-0001"]["epss_percentile"]) == (0.5, 0.9)
    assert vulns["CVE-2024-0001"]["vendor"] == "Vendor"
    assert vulns["CVE-2025-0002"]["epss"] is None


def test_an_out_of_range_epss_score_is_not_published():
    payload = _busy_world(epss=B("epss", vulns=[V("CVE-2024-0001", epss=1.5, percentile=0.9)]))
    row = {v["cve"]: v for v in payload["vulns.json"]}["CVE-2024-0001"]
    assert (row["epss"], row["epss_percentile"]) == (None, 0.9)


def test_epss_is_not_published_when_its_policy_says_so():
    payload = _busy_world(policies={"epss": "evidence-only"},
                          epss=B("epss", vulns=[V("CVE-2024-0001", epss=0.5, percentile=0.9)]))
    assert {v["epss"] for v in payload["vulns.json"]} == {None}


def test_kev_is_not_published_when_its_policy_says_so_but_report_cves_still_are():
    payload = run(*WORLD(kev=B("kev", vulns=[V("CVE-2024-0001", "2024-02-01", True)]),
                         orkl=B("orkl", reports=[R("orkl", "1", "R", "https://ex.org/1", "2025-01-01",
                                                   cves=["CVE-2024-0001"])])),
                  policies={"kev": "evidence-only"})
    assert payload["vulns.json"] == [{"cve": "CVE-2024-0001", "kev_date_added": None, "ransomware": None,
                                      "vendor": None, "product": None, "actors": [], "report_count": 1,
                                      "epss": None, "epss_percentile": None}]
    assert payload["trends.json"]["kev_monthly"] == []


def test_kev_monthly_counts_additions_per_month_with_ransomware_subtotals():
    kev = B("kev", vulns=[V("CVE-2025-0001", "2025-01-05", True), V("CVE-2025-0002", "2025-01-20", False),
                          V("CVE-2025-0003", "2025-01-21", None), V("CVE-2025-0004", "2025-03-02", True)])
    months = {m["month"]: m for m in run(*WORLD(kev=kev))["trends.json"]["kev_monthly"]}
    assert months["2025-01"] == {"month": "2025-01", "added": 3, "ransomware": 1}
    assert months["2025-02"] == {"month": "2025-02", "added": 0, "ransomware": 0}
    assert months["2025-03"] == {"month": "2025-03", "added": 1, "ransomware": 1}


# Campaigns

def test_campaigns_keep_only_published_actors():
    campaigns = run(*WORLD())["campaigns.json"]
    assert campaigns == [{"id": "C0001", "name": "Operation Blue", "first_seen": "2019-09-01",
                          "last_seen": "2020-01-01", "actors": ["G0007"], "techniques": ["T1059"],
                          "source": "attack"}]


# New actors

def test_an_actor_first_seen_within_a_year_is_new_and_one_from_2019_is_not():
    attack = B("attack", actors=[A("attack", "G0007", "APT28"), A("attack", "G0016", "APT29")],
               campaigns=[C("C1", "Recent", ["G0007"], first_seen="2026-03-01"),
                          C("C2", "Old", ["G0016"], first_seen="2019-03-01"),
                          C("C3", "Recent again", ["G0016"], first_seen="2026-04-01")])
    assert run(attack)["trends.json"]["new_actors"] == [
        {"actor": "G0007", "first_seen": "2026-03-01", "basis": "attack"}]


def test_a_year_only_etda_first_seen_counts_as_january_first_of_that_year():
    def new(year):
        etda = B("etda", actors=[A("etda", "e1", "APT28", first_seen=[year])])
        return run(B("attack", actors=[A("attack", "G0007", "APT28")]), etda)["trends.json"]["new_actors"]
    assert new("2026") == [{"actor": "G0007", "first_seen": "2026-01-01", "basis": "year"}]
    # 2025 began before the 365-day window, so the actor may have appeared earlier than the window.
    assert new("2025") == []
    assert new("2004") == []


def test_an_etda_actor_with_only_a_year_is_not_silently_dropped():
    etda = B("etda", actors=[A("etda", "e1", "Fresh Actor", first_seen=["2026"])])
    payload = run(etda)
    assert payload["trends.json"]["new_actors"] == [
        {"actor": "fresh-actor", "first_seen": "2026-01-01", "basis": "year"}]


def test_a_full_date_from_a_source_keeps_that_source_as_its_basis():
    misp = B("misp", actors=[A("misp", "m1", "Fresh Actor", first_seen=["2026-04-02"])])
    assert run(misp)["trends.json"]["new_actors"] == [
        {"actor": "fresh-actor", "first_seen": "2026-04-02", "basis": "misp"}]


# Sources, resolution and build

def test_sources_json_lists_every_source_with_its_policy_and_credit():
    payload = run(*WORLD())
    rows = {s["name"]: s for s in payload["sources.json"]}
    assert list(rows) == list(SOURCE_ORDER)
    assert rows["etda"]["publish"] == "derived-only" and rows["orkl"]["publish"] == "link-only"
    assert rows["attack"]["attribution"] == source_attribution("attack", "2026")
    assert rows["attack"]["licence"] == "MITRE ATT&CK® Terms of Use"
    assert rows["attack"]["record_count"] == 2
    assert rows["misp"]["record_count"] == 2
    assert all(s["last_success"] == SNAP and s["stale"] is False for s in rows.values())


def test_etda_health_reports_the_date_its_database_last_changed():
    facts = replace(FACTS, etda_last_db_change="2025-08-16")
    rows = {s["name"]: s for s in run(*WORLD(), facts=facts)["sources.json"]}
    assert rows["etda"]["last_success"] == "2025-08-16"
    assert rows["misp"]["last_success"] == SNAP
    health = {s["name"]: s for s in run(*WORLD(), facts=facts)["trends.json"]["source_health"]}
    assert health["etda"]["last_success"] == "2025-08-16"


def test_a_failed_fetch_or_a_missing_snapshot_is_stale():
    dates = {key: SNAP for key in SOURCE_ORDER}
    dates["paper"] = None
    facts = replace(FACTS, snapshot_dates=dates, fetch_failed=frozenset({"dfir"}))
    rows = {s["name"]: s for s in run(*WORLD(), facts=facts)["sources.json"]}
    assert rows["dfir"]["stale"] is True and rows["dfir"]["last_success"] == SNAP
    assert rows["paper"]["stale"] is True and rows["paper"]["last_success"] is None
    assert rows["misp"]["stale"] is False


def test_resolution_reports_the_registry_and_the_paper_match():
    world = WORLD()
    facts = replace(FACTS, paper_names=["Sofacy", "Fancy Bear", "Mimikatz", "Nobody", "Sofacy"])
    world[0] = world[0].model_copy(update={"software": [SoftwareRecord(
        source="attack", source_id="S1", name="Mimikatz", kind="tool", retrieved_at=SNAP)]})
    registry = resolve([a for b in world for a in b.actors], world[0].software)
    payload = assemble(world, registry, POLICIES, generated_at=NOW, facts=facts)
    resolution = payload["resolution.json"]
    assert resolution["stats"] == registry.stats()
    assert resolution["paper_match"] == {"names_total": 4, "resolved": 2, "typed_non_actor": 1,
                                         "match_rate": 0.5}
    assert resolution["ambiguities"] == registry.ambiguities


def test_paper_match_rate_is_null_when_the_paper_is_unavailable():
    assert run(*WORLD())["resolution.json"]["paper_match"] == {
        "names_total": 0, "resolved": 0, "typed_non_actor": 0, "match_rate": None}


def test_unresolved_names_are_counted_per_report_most_frequent_first_and_capped_at_200():
    reports = [R("paper", f"{i}.pdf", f"Report {i}", f"https://ex.org/{i}", "2019-05-01",
                 actor_names=[f"Crew {i % 250:03d}", "Everywhere"]) for i in range(300)]
    payload = run(*WORLD(paper=B("paper", reports=reports)))
    names = payload["resolution.json"]["unresolved_names"]
    assert len(names) == 200
    assert names[0] == {"name": "Everywhere", "count": 300, "typed_as": None}
    assert [n["count"] for n in names] == sorted((n["count"] for n in names), reverse=True)


def test_build_json_says_when_and_which_shards():
    orkl = B("orkl", reports=[R("orkl", "1", "A", "https://ex.org/a", "2025-05-01"),
                              R("orkl", "2", "B", "https://ex.org/b", "2023-05-01"),
                              R("orkl", "3", "C", "https://ex.org/c", "2025-06-01")])
    payload = run(*WORLD(orkl=orkl))
    assert payload["build.json"]["built_at"] == NOW
    assert payload["build.json"]["report_years"] == [2023, 2025]
    assert payload["build.json"]["report_count"] == 3
    assert payload["build.json"]["recent_since"] == payload["trends.json"]["window_start"]
    assert payload["build.json"]["recent_months"] == trends.WINDOW_MONTHS
    assert payload["build.json"]["version"]


def test_the_reports_index_lists_every_report_and_carries_the_build_time():
    orkl = B("orkl", reports=[R("orkl", "1", "A", "https://ex.org/a", "2025-05-01"),
                              R("orkl", "2", "B", "https://ex.org/b", "2023-05-01"),
                              R("orkl", "3", "C")])
    payload = run(*WORLD(orkl=orkl))
    index = payload["reports/index.json"]
    rows = all_report_rows(payload)
    assert index["built_at"] == payload["build.json"]["built_at"] == NOW
    assert index["total"] == len(rows) == len(index["columns"]["id"])
    assert sorted(index["columns"]["title"]) == sorted(r["title"] for r in rows)
    assert index["columns"]["published"] == sorted((p for p in index["columns"]["published"] if p),
                                                   reverse=True) + [None] * index["columns"]["published"].count(None)


def test_the_reports_index_marks_kev_cves_from_the_vulnerability_list():
    payload = run(*WORLD())
    kev = {v["cve"] for v in payload["vulns.json"] if v["kev_date_added"] is not None}
    table = payload["reports/index.json"]["tables"]["cves"]
    assert {table[i] for i in payload["reports/index.json"]["kev"]} == kev & set(table)


def test_actor_file_names_are_safe_on_a_case_insensitive_file_system():
    misp = B("misp", actors=[A("misp", "1", "Ünïcode Bear"), A("misp", "2", "熊猫"), A("misp", "3", "Index")])
    payload = run(misp)
    for rel in actor_files(payload):
        stem = rel[len("actors/"):-len(".json")]
        assert stem == stem.lower() or stem.startswith("G")
    assert "actors/index.json" in payload and isinstance(payload["actors/index.json"], list)


# Slug registry

def test_the_payload_carries_a_slug_entry_for_every_published_actor():
    payload = run(*WORLD())
    entries = {e["slug"]: e for e in payload["slugs.json"]["entries"]}
    assert set(actor_files(payload)) == {f"actors/{s}.json" for s, e in entries.items() if not e["retired"]}
    assert entries["G0007"]["display_name"] == "APT28"
    assert entries["G0007"]["first_published"] == NOW[:10]


def test_a_hidden_source_never_shapes_a_slug_or_an_anchor():
    misp = B("misp", actors=[A("misp", "hidden-1", "Secret Panda")])
    payload = run(misp, policies={"misp": "evidence-only"})
    assert payload["slugs.json"]["entries"] == []


def test_a_registry_resolved_with_the_wrong_visible_sources_is_refused():
    misp = B("misp", actors=[A("misp", "1", "Glass Heron")])
    registry = resolve(list(misp.actors), [])
    with pytest.raises(ValueError, match="visible sources"):
        assemble([misp], registry, {**POLICIES, "misp": "evidence-only"}, generated_at=NOW, facts=FACTS)
