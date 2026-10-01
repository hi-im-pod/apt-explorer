import re
from pathlib import Path

import pytest

from aptx.build.notice import SOURCE_INFO, SOURCE_ORDER, render_notice, source_attribution
from aptx.sources.base import SOURCES_MD

FIXTURES = Path(__file__).parent / "fixtures"
LABEL = re.compile(r"\S(.*\S)?")


def _lf(text: str) -> str:
    # A Windows checkout may turn the fixture's line ends into CRLF.
    return text.replace("\r\n", "\n")


def test_the_2026_notice_matches_the_committed_wording_byte_for_byte():
    golden = _lf((FIXTURES / "NOTICE_2026.md").read_text(encoding="utf-8"))
    assert render_notice("2026") == golden


def test_only_the_copyright_year_changes_with_the_year():
    golden = _lf((FIXTURES / "NOTICE_2026.md").read_text(encoding="utf-8"))
    later = render_notice("2027")
    assert "© 2027 The MITRE Corporation." in later
    assert "© 2026" not in later
    assert later == golden.replace("© 2026 The MITRE Corporation", "© 2027 The MITRE Corporation")


@pytest.mark.parametrize("year", [None, "", "26", "20x6", "2026 ", "MMXXVI"])
def test_a_missing_or_malformed_year_stops_the_build(year):
    # MITRE's licence requires its own designation in every copy, so a guessed
    # year would be a false statement about who holds the copyright.
    with pytest.raises(ValueError, match="copyright"):
        render_notice(year)


def test_every_source_is_credited_once_in_a_fixed_order():
    text = render_notice("2026")
    assert SOURCE_ORDER == ("attack", "misp", "etda", "malpedia", "orkl", "kev", "dfir", "paper", "microsoft", "epss",
                            "talos", "eset", "microsoftblog")
    assert set(SOURCE_INFO) == set(SOURCE_ORDER)
    for key in SOURCE_ORDER[1:]:
        assert text.count(f"(`{key}`)") == 1
    positions = [text.index(f"(`{key}`)") for key in SOURCE_ORDER[1:]]
    assert positions == sorted(positions)


def test_the_notice_states_the_data_licence_and_that_no_extra_terms_apply():
    text = render_notice("2026")
    assert "CC BY-NC-SA 4.0" in text
    assert "https://creativecommons.org/licenses/by-nc-sa/4.0/" in text
    assert "No additional terms or conditions apply to these files." in text


def test_the_related_work_line_points_at_apt_map_and_says_nothing_about_its_terms():
    # A pointer to a neighbouring project is a credit, not a licence statement. It must not
    # imply the project's licence, its maintainers' approval or any plan to contribute.
    text = render_notice("2026")
    lines = [line for line in text.split("\n") if line.startswith("Related work:")]
    assert len(lines) == 1
    assert "https://lngt-apt-study-map.vercel.app/" in lines[0]
    # It says what kind of map it is, which the person who built it can check.
    assert "hand-curated incident rows" in lines[0]
    for word in ("licen", "approv", "endors", "permission", "contribut", "affiliat"):
        assert word not in lines[0].lower()
    # The line sits in the intro, before the first section heading.
    assert text.index(lines[0]) < text.index("## MITRE ATT&CK")


def test_the_licence_paragraph_and_trademark_line_travel_with_the_designation():
    text = render_notice("2026")
    assert "reproduce MITRE's copyright designation and this license in any such copy." in text
    assert "MITRE ATT&CK® and ATT&CK® are registered trademarks of The MITRE Corporation." in text


def test_each_credit_is_the_wording_sources_md_records():
    """A drift guard: if SOURCES.md changes an attribution, this fails until the code follows."""
    sources_md = SOURCES_MD.read_text(encoding="utf-8-sig")
    for key, info in SOURCE_INFO.items():
        for paragraph in (*info.paragraphs("2026"), *([info.extra] if info.extra else [])):
            assert paragraph in sources_md, f"{key}: {paragraph[:60]!r} is not in SOURCES.md"


@pytest.mark.parametrize("key", SOURCE_ORDER)
def test_the_joined_attribution_is_one_line_the_schema_accepts(key):
    line = source_attribution(key, "2026")
    assert "\n" not in line
    assert LABEL.fullmatch(line)


def test_the_attack_attribution_carries_the_year_and_the_others_do_not_need_one():
    assert source_attribution("attack", "2031").startswith("© 2031 The MITRE Corporation. This work is reproduced")
    assert source_attribution("misp", None) == source_attribution("misp", "2031")
    with pytest.raises(ValueError, match="copyright"):
        source_attribution("attack", None)
