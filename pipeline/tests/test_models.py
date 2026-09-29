import pytest
from pydantic import ValidationError
from aptx.core.models import (ActorRecord, CampaignRecord, Claim, Provenance, ReportRecord,
                              SoftwareRecord, SourceBundle, VulnRecord)

def test_list_and_optional_fields_default_to_empty():
    a = ActorRecord(source="misp", source_id="u1", name="APT1", retrieved_at="2026-09-29")
    assert a.aliases == [] and a.origin == [] and a.techniques == []
    r = ReportRecord(source="dfir", source_id="x", title="T", date_basis="publisher", retrieved_at="2026-09-29")
    assert r.published is None and r.url is None and r.actor_names == []
    c = CampaignRecord(source="attack", source_id="C0001", name="C", retrieved_at="2026-09-29")
    assert c.first_seen is None and c.actor_refs == []
    v = VulnRecord(cve="CVE-2023-23397", retrieved_at="2026-09-29")
    assert v.ransomware is None
    b = SourceBundle(source="kev")
    assert b.actors == b.reports == b.campaigns == b.vulns == b.software == []

def test_default_lists_are_not_shared_between_records():
    a = ActorRecord(source="misp", source_id="u1", name="A", retrieved_at="x")
    a.aliases.append("B")
    assert ActorRecord(source="misp", source_id="u2", name="C", retrieved_at="x").aliases == []

def test_misspelled_field_is_rejected_not_dropped():
    with pytest.raises(ValidationError):
        ReportRecord(source="orkl", source_id="1", title="T", date_basis="unknown",
                     retrieved_at="x", archiveUrl="https://example.test/a.pdf")

def test_software_kind_is_malware_or_tool_only():
    with pytest.raises(ValidationError):
        SoftwareRecord(source="attack", source_id="S1", name="X", kind="actor", retrieved_at="x")

def test_claim_is_generic_over_its_value():
    prov = Provenance(source="misp", source_id="u1", retrieved_at="2026-09-29")
    assert Claim[str](value="Fancy Bear", prov=prov).value == "Fancy Bear"
    with pytest.raises(ValidationError):
        Claim[int](value="not a number", prov=prov)


def test_software_attribution_defaults_to_empty_and_is_not_shared():
    a = SoftwareRecord(source="malpedia", source_id="win.x", name="X", kind="malware", retrieved_at="x")
    assert a.attribution == []
    a.attribution.append("APT 29")
    assert SoftwareRecord(source="malpedia", source_id="win.y", name="Y", kind="malware",
                          retrieved_at="x").attribution == []
