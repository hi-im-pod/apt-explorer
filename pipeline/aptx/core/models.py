"""The shared records every connector normalizes into.

Each record keeps the source and the source's own ID next to its values, so any
fact on the site can be traced back to the source that asserted it.
"""
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class _Record(BaseModel):
    # Pydantic drops unknown fields by default. A misspelled field such as
    # archiveUrl would then vanish without an error, so unknown fields are
    # refused instead.
    model_config = ConfigDict(extra="forbid")


class Provenance(_Record):
    source: str
    source_id: str
    retrieved_at: str


class Claim(_Record, Generic[T]):
    """One value together with the source that asserted it.

    Sources often disagree, so every value keeps its provenance. The site can
    then show each claim and flag disagreements rather than pick a winner.
    """
    value: T
    prov: Provenance


class ActorRecord(_Record):
    source: str
    source_id: str
    name: str
    aliases: list[str] = []
    origin: list[str] = []
    sponsor: list[str] = []
    motivation: list[str] = []
    targets_countries: list[str] = []
    targets_sectors: list[str] = []
    first_seen: list[str] = []
    malware: list[str] = []
    techniques: list[str] = []
    retrieved_at: str


class ReportRecord(_Record):
    source: str
    source_id: str
    title: str
    published: str | None = None
    # date_basis is required even when published is None. A reader must always
    # know where a report's date came from, including when there is none.
    date_basis: str
    organisation: str | None = None
    url: str | None = None
    archive_url: str | None = None
    sha1: str | None = None
    actor_names: list[str] = []
    cves: list[str] = []
    techniques: list[str] = []
    retrieved_at: str


class CampaignRecord(_Record):
    source: str
    source_id: str
    name: str
    first_seen: str | None = None
    last_seen: str | None = None
    actor_refs: list[str] = []
    techniques: list[str] = []
    report_urls: list[str] = []
    retrieved_at: str


class VulnRecord(_Record):
    cve: str
    kev_date_added: str | None = None
    # None means the source does not say. That is different from False, which
    # means the source says there is no known ransomware use.
    ransomware: bool | None = None
    vendor: str | None = None
    product: str | None = None
    retrieved_at: str


class SoftwareRecord(_Record):
    source: str
    source_id: str
    name: str
    aliases: list[str] = []
    # The resolver uses this to type a name as malware or a tool, so it does
    # not treat that name as an actor.
    kind: Literal["malware", "tool"]
    # The actor names a source attributes this software to, verbatim. Malpedia
    # has 73 such names that match no actor's display name exactly, and the
    # resolver can use them to link the software to an actor. This is an
    # internal field; no published schema carries it.
    attribution: list[str] = []
    retrieved_at: str


class SourceBundle(_Record):
    """Everything one connector produced in one normalize pass."""
    source: str
    actors: list[ActorRecord] = []
    reports: list[ReportRecord] = []
    campaigns: list[CampaignRecord] = []
    vulns: list[VulnRecord] = []
    software: list[SoftwareRecord] = []
