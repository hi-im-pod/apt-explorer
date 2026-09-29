import re
from pathlib import Path

import pytest
from aptx.core.dates import parse_date
from aptx.core.models import SourceBundle
from aptx.sources import base
from aptx.sources.base import publish_policy, now_iso

FIX = Path(__file__).parent / "fixtures" / "SOURCES.md"


@pytest.mark.parametrize("name, expected", [
    ("attack", "full"),
    ("misp", "derived-only"),       # bold markup around the value
    ("etda", "evidence-only"),      # backticks around the value
    ("dfir", "link-only"),          # an escaped pipe earlier in the row
    ("paper", "full"),              # the first cell is the bare key
    ("kev", "full"),                # a second table with fewer columns
])
def test_reads_the_publish_column_of_the_matching_row(name, expected):
    assert publish_policy(name, FIX) == expected


def test_unrecognised_value_fails_closed():
    assert publish_policy("malpedia", FIX) == "evidence-only"


def test_source_without_a_row_is_evidence_only():
    assert publish_policy("orkl", FIX) == "evidence-only"


def test_missing_file_is_evidence_only(tmp_path):
    assert publish_policy("etda", tmp_path / "SOURCES.md") == "evidence-only"


def test_human_name_alone_does_not_match(tmp_path):
    p = tmp_path / "SOURCES.md"
    p.write_text("| Source | publish |\n|---|---|\n| MITRE ATT&CK | full |\n", encoding="utf-8")
    assert publish_policy("attack", p) == "evidence-only"


def test_column_must_be_named_publish_exactly(tmp_path):
    # The spec's own table has a "Republish derived facts?" column, which is
    # not the licence gate.
    p = tmp_path / "SOURCES.md"
    p.write_text("| Source | Republish derived facts? |\n|---|---|\n| `kev` | full |\n", encoding="utf-8")
    assert publish_policy("kev", p) == "evidence-only"


def test_bom_and_crlf_are_tolerated(tmp_path):
    p = tmp_path / "SOURCES.md"
    p.write_bytes("﻿| Source | publish |\r\n|---|---|\r\n| ATT&CK® (`attack`) | full |\r\n".encode("utf-8"))
    assert publish_policy("attack", p) == "full"


def test_fallback_is_logged_so_a_missed_row_is_visible(tmp_path, caplog):
    with caplog.at_level("WARNING"):
        publish_policy("orkl", FIX)
    assert "orkl" in caplog.text


def test_default_path_is_the_repository_root():
    assert base.SOURCES_MD == Path(__file__).resolve().parents[2] / "SOURCES.md"


def test_a_plain_class_satisfies_the_connector_protocol():
    class Fake:
        name = "fake"
        def fetch(self, store): pass
        def normalize(self, store): return SourceBundle(source="fake")
    assert isinstance(Fake(), base.Connector)
    assert not isinstance(object(), base.Connector)


def test_now_iso_is_utc_seconds_with_z():
    t = now_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", t)
    assert parse_date(t) == t[:10]
