"""Names that titles repeat: which phrases count as name-shaped, and what the words around a name say."""
from aptx.resolve.names import norm
from aptx.resolve.title_terms import Title, TitleIndex


def titles(*texts):
    return [Title(f"t{i}", t, "2024-01-01", None, f"https://example.org/{i}") for i, t in enumerate(texts)]


def found(texts, known=lambda name: False, minimum=3):
    index = TitleIndex(titles(*texts))
    return {c.name for c in index.candidates(known, minimum_titles=minimum).values()}


def repeat(template, n=3):
    return [template] * n


def test_each_structural_shape_is_found():
    texts = (repeat("UNC9999 targets banks") + repeat("Storm-0001 phishing wave") + repeat("Salt Quasar Typhoon returns")
             + repeat("Marigold Group hits telecoms") + repeat("Zorklo Stealer spreads") + repeat("New ToddyCat tooling")
             + repeat("Notes on the Larkspur threat actor"))
    names = found(texts)
    assert {"UNC9999", "Storm-0001", "Marigold", "Zorklo", "ToddyCat", "Larkspur"} <= names
    assert any("Typhoon" in n for n in names)


def test_a_phrase_must_be_in_enough_titles():
    texts = repeat("Zorklo Stealer spreads", 2)
    assert found(texts) == set()
    assert "Zorklo" in found(texts, minimum=2)


def test_ordinary_capitalised_words_are_not_names():
    texts = repeat("The New Security Report On Ransomware Groups") + repeat("Microsoft And Google Warn Of Windows Flaw")
    assert found(texts) == set()


def test_a_word_the_titles_use_in_lower_case_is_ordinary():
    texts = repeat("Quillfoo Stealer found") + ["we saw quillfoo again"] * 20
    assert "Quillfoo" not in found(texts)


def test_a_known_name_is_dropped_whatever_its_spelling():
    texts = repeat("Zorklo Stealer spreads") + repeat("ToddyCat tooling")
    names = found(texts, known=lambda name: norm(name) == norm("Zorklo"))
    assert "Zorklo" not in names and "ToddyCat" in names


def test_a_title_with_a_corrupted_character_is_not_read():
    index = TitleIndex(titles("Zorklo � Stealer", "Zorklo Stealer", "https://example.org/x"))
    assert [t.text for t in index.titles] == ["Zorklo Stealer"]


def test_stats_count_a_title_once_and_read_the_context():
    index = TitleIndex(titles(
        "Zorklo Stealer targets banks",
        "Zorklo threat actor returns",
        "Zorklo and Zorklo again",
        "Unrelated title",
    ))
    stat = index.stats(["Zorklo"])[norm("Zorklo")]
    assert stat.titles == 3
    assert stat.malware_titles == 1
    assert stat.actor_titles == 1


def test_stats_match_whole_words_only():
    index = TitleIndex(titles("Zorklos arrive", "Pre Zorklo post"))
    assert index.stats(["Zorklo"])[norm("Zorklo")].titles == 1
