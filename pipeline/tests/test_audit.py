from aptx.audit import generic_titles, merge_candidates, norm_title, redate


def row(rid, title, url, published="2020-01-01", basis="malpedia-library", **kw):
    return {"id": rid, "title": title, "url": url, "published": published, "date_basis": basis,
            "actors": [], "actors_from_text": [], "cves": [], "techniques": [], "sources": ["orkl"], **kw}


def test_titles_are_compared_after_cleaning_case_and_punctuation():
    assert norm_title("Who's behind the GPcode ransomware?") == norm_title("Who's behind the GPcode ransomware-")
    assert norm_title("Microsoft Word - TR62.doc") == "tr62"


def test_an_ingest_dated_row_takes_the_date_in_its_address():
    assert redate(row("a", "t", "https://ex.org/2021/05/31/p", "2026-04-06", "orkl-ingest")) == ("2021-05-31", "url-date")
    assert redate(row("a", "t", "https://ex.org/p", "2026-04-06", "orkl-ingest")) == ("2026-04-06", "orkl-ingest")


def test_a_title_four_pages_on_one_host_share_is_generic_and_spread_copies_are_not():
    same_host = [row(str(n), "Secure Communications Blog", f"https://blogs.ex.com/p{n}") for n in range(4)]
    spread = [row(f"s{n}", "Conti ransomware", f"https://h{n}.ex/p") for n in range(6)]
    assert list(generic_titles(same_host + spread)) == ["blogs.ex.com | secure communications blog"]


def test_the_strict_merge_needs_a_long_title_and_close_dates():
    rows = [row("a", "Agent.btz - A Threat That Hit Pentagon", "https://a.ex/1", "2008-11-30"),
            row("b", "Agent.btz - A Threat That Hit Pentagon", "https://b.ex/1", "2008-12-05"),
            row("c", "Agent.btz - A Threat That Hit Pentagon", "https://c.ex/1", "2012-01-01"),
            row("d", "Diavol ransomware", "https://a.ex/2"), row("e", "Diavol ransomware", "https://b.ex/2")]
    assert [[r["id"] for r in g] for g in merge_candidates(rows, set())] == [["a", "b"]]
