"""terms.json: which repeated names are published, with what counts, and what is left out."""
import pytest

from aptx.build import terms
from aptx.resolve.title_terms import Title, TitleIndex


def title(i, text, published="2024-03-01", organisation=None, url=None):
    return Title(f"r{i}", text, published, organisation, url if url is not None else f"https://www.pub{i}.org/{i}")


class Model:
    """Stands in for a fitted model. The guess is a fixed label, so these tests are about the counts."""


@pytest.fixture(autouse=True)
def fixed_guess(monkeypatch):
    def guess(name, count, prepared):
        label = "not-an-entity" if name == "Nothing" else "malware"
        return {"name": name, "count": count, "label": label, "confidence": None, "band": "unvalidated",
                "matched_actor_id": None, "matched_actor_name": None, "evidence": [], "status": "pending confirmation"}
    monkeypatch.setattr(terms.guesses, "guess_name", guess)


def build(titles_, prepared=Model()):
    index = TitleIndex(titles_)
    candidates = terms.find_candidates(index, lambda n: False)
    stats = index.stats([c.name for c in candidates.values()])
    return terms.build_terms(index, candidates, stats, prepared)


def test_publisher_is_the_organisation_else_the_registrable_host():
    assert terms.publisher_key(title(1, "x", organisation=" ESET ")) == "org:eset"
    assert terms.publisher_key(title(1, "x", url="https://www.blog.example.org/a")) == "host:example.org"
    assert terms.publisher_key(title(1, "x", url="https://news.example.co.uk/a")) == "host:example.co.uk"
    assert terms.publisher_key(title(1, "x", url="")) is None


def test_a_term_needs_three_reports_from_two_publishers():
    one_publisher = [title(i, "Zorklo Stealer spreads", url=f"https://blog{i}.same.org/{i}") for i in range(3)]
    assert build(one_publisher)["terms"] == []
    two_reports = [title(i, "Zorklo Stealer spreads") for i in range(2)]
    assert build(two_reports)["terms"] == []
    enough = [title(i, "Zorklo Stealer spreads") for i in range(3)]
    doc = build(enough)
    assert [t["name"] for t in doc["terms"]] == ["Zorklo"]
    assert doc["terms"][0]["reports"] == 3 and doc["terms"][0]["publishers"] == 3
    assert doc["min_reports"] == 3 and doc["min_publishers"] == 2 and doc["titles_read"] == 3


def test_an_organisation_counts_as_one_publisher_across_hosts():
    same_org = [title(i, "Zorklo Stealer spreads", organisation="ESET") for i in range(3)]
    assert build(same_org)["terms"] == []


def test_years_dates_and_examples():
    rows = [title(1, "Zorklo Stealer a", "2022-05-01"), title(2, "Zorklo Stealer b", "2024-01-09"),
            title(3, "Zorklo Stealer c", "2024-03-02"), title(4, "Zorklo Stealer d", "2024-02-02", url="")]
    term = build(rows)["terms"][0]
    assert term["first_seen"] == "2022-05-01" and term["last_seen"] == "2024-03-02"
    assert term["by_year"] == [{"year": 2022, "count": 1}, {"year": 2024, "count": 3}]
    assert len(term["examples"]) == 3
    assert all(e["url"] for e in term["examples"])
    dates = [e["published"] for e in term["examples"]]
    assert dates == sorted(dates, reverse=True)


def test_examples_prefer_different_publishers():
    rows = [title(i, "Zorklo Stealer x", f"2024-0{i + 1}-01", url=f"https://a-pub.org/{i}") for i in range(3)]
    rows.append(title(9, "Zorklo Stealer y", "2020-01-01", url="https://b-pub.org/9"))
    hosts = {terms.publisher_key(Title("", "", None, None, e["url"])) for e in build(rows)["terms"][0]["examples"]}
    assert "host:b-pub.org" in hosts


def test_no_model_means_no_terms():
    rows = [title(i, "Zorklo Stealer spreads") for i in range(3)]
    doc = build(rows, prepared=None)
    assert doc["terms"] == [] and doc["hidden_as_not_names"] == 0 and doc["titles_read"] == 3


def test_a_phrase_the_guesser_calls_not_a_name_is_hidden_and_counted():
    rows = ([title(i, "Nothing Stealer spreads") for i in range(3)]
            + [title(i + 5, "Zorklo Stealer spreads") for i in range(3)])
    doc = build(rows)
    assert [t["name"] for t in doc["terms"]] == ["Zorklo"]
    assert doc["hidden_as_not_names"] == 1


def test_terms_are_ordered_by_reports_then_publishers_then_name():
    rows = ([title(i, "Zorklo Stealer spreads") for i in range(3)]
            + [title(i + 10, "Marigold Stealer spreads") for i in range(5)])
    assert [t["name"] for t in build(rows)["terms"]] == ["Marigold", "Zorklo"]


class Report:
    def __init__(self, i, title, readable, url=None):
        self.id, self.title, self.published, self.organisation = f"r{i}", title, "2024-01-01", None
        self.url = url if url is not None else f"https://x{i}.example.org"
        self.title_readable = readable


def test_only_readable_titles_that_are_not_just_a_link_are_used():
    reports = [Report(1, "A title", True), Report(2, "Hidden title", False),
               Report(3, "https://x3.example.org", True, url="https://x3.example.org")]
    assert [t.text for t in terms.titles_from_reports(reports)] == ["A title"]
