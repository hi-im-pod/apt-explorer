import csv
from pathlib import Path

import pytest

LAB = Path(__file__).parent / "fixtures" / "paper_unresolved_labels.csv"

# The file is generated from live snapshots and reviewed by hand, so a checkout that has not
# generated it yet skips the test instead of failing.
@pytest.mark.skipif(not LAB.exists(), reason="labels not generated yet")
def test_labelled_set_is_well_formed():
    with LAB.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == ["name", "label", "prefill_basis"]
        rows = list(reader)
    assert len(rows) >= 100
    assert {r["label"] for r in rows} <= {"actor", "malware", "tool", "unknown", "not-an-entity"}
    names = [r["name"] for r in rows]
    assert all(n == n.strip() and n for n in names), "names are trimmed and not empty"
    assert len(set(names)) == len(names), "each name is labelled once"
    assert all(r["prefill_basis"].strip() for r in rows), "every label says what it was prefilled from"
