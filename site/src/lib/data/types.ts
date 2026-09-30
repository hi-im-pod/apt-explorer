/**
 * Types for the JSON the pipeline publishes under data/.
 *
 * They mirror the JSON Schemas in pipeline/aptx/build/schemas/ field for
 * field. The schemas are the contract: the pipeline validates every file
 * against them before writing it, and pipeline/tests/test_contract_types.py
 * fails when this file and the schemas drift apart. Each interface and union
 * names the schema node it mirrors in an @schema tag, which is how that test
 * pairs them, so keep the tags when editing. A change here needs the same
 * change in the schema first.
 *
 * Every field is always present. A value that no source supplies is null,
 * never a missing key, so the site checks for null rather than undefined.
 */

// ---------------------------------------------------------------------------
// Scalars. The schemas pin each format with a pattern; TypeScript cannot, so
// these names document the format instead.

/** A connector key such as "attack" or "misp", as listed in sources.json. Never a display name. */
export type SourceKey = string;

/** An ATT&CK group ID such as "G0007", or a lower-case slug. Also the actor's file name and URL segment. */
export type ActorId = string;

/** A report's SHA-1 when one is known, otherwise "<source>:<source_id>". Used in ?report= links. */
export type ReportId = string;

/** An ATT&CK campaign ID such as "C0022", or a source-scoped ID. Used in ?campaign= links. */
export type CampaignId = string;

/** A calendar date, YYYY-MM-DD, never earlier than 1990. */
export type IsoDate = string;

/** A UTC timestamp, YYYY-MM-DDTHH:MM:SSZ. */
export type IsoDateTime = string;

/** A calendar quarter, YYYY-Qn. */
export type Quarter = string;

/** A calendar month, YYYY-MM. */
export type Month = string;

/** An upper-case CVE ID such as "CVE-2023-23397". */
export type CveId = string;

/** An ATT&CK technique or sub-technique ID such as "T1059.001". */
export type TechniqueId = string;

// ---------------------------------------------------------------------------
// Closed sets of values.

/**
 * What SOURCES.md allows the site to publish from a source. Nothing from an
 * evidence-only source appears in data/; such a source only helps merge actors.
 * @schema sources.schema.json#/$defs/publish
 */
export type PublishPolicy = 'full' | 'derived-only' | 'evidence-only' | 'link-only';

/**
 * Where a report's date came from. 'unknown' always comes with published: null,
 * and any other basis comes with a date.
 * @schema reports_shard.schema.json#/$defs/dateBasis
 */
export type DateBasis =
	| 'malpedia-library'
	| 'file-metadata'
	| 'orkl-ingest'
	| 'publisher'
	| 'paper'
	| 'unknown';

/**
 * The actor field that published sources disagree on.
 * @schema actor.schema.json#/$defs/conflict/properties/field
 */
export type ConflictField = 'origin' | 'sponsor' | 'motivation';

/**
 * How the registry typed a name that is software rather than an actor.
 * @schema resolution.schema.json#/$defs/unresolvedName/properties/typed_as
 */
export type SoftwareKind = 'malware' | 'tool';

// ---------------------------------------------------------------------------
// actors/index.json

/**
 * One published actor, as listed and searched on /actors.
 * @schema actors_index.schema.json#/$defs/entry
 */
export interface ActorsIndexEntry {
	id: ActorId;
	name: string;
	/** In the order the actor page lists them. May hold very long unbroken strings. */
	aliases: string[];
	/** Distinct values across sources. More than one means the sources disagree. */
	origin: string[];
	report_count: number;
	/** Null when none of the actor's reports is dated. */
	last_reported: IsoDate | null;
	sources: SourceKey[];
}

/**
 * The whole of actors/index.json.
 * @schema actors_index.schema.json#
 */
export type ActorsIndex = ActorsIndexEntry[];

// ---------------------------------------------------------------------------
// actors/<id>.json

/**
 * One alias and every published source that asserts it.
 * @schema actor.schema.json#/$defs/aliasClaim
 */
export interface AliasClaim {
	value: string;
	sources: SourceKey[];
}

/**
 * One value and the source that asserts it.
 * @schema actor.schema.json#/$defs/sourcedValue
 */
export interface SourcedValue {
	value: string;
	source: SourceKey;
}

/**
 * Countries and sectors the sources say the actor targets. These are
 * actor-level claims, not facts about any one campaign, and the page labels
 * them that way.
 * @schema actor.schema.json#/$defs/claimedTargets
 */
export interface ClaimedTargets {
	countries: SourcedValue[];
	sectors: SourcedValue[];
}

/**
 * A malware family or tool and the source that links it to the actor.
 * @schema actor.schema.json#/$defs/malwareClaim
 */
export interface MalwareClaim {
	name: string;
	source: SourceKey;
}

/**
 * A technique and how many of the actor's reports from 2024 on name it.
 * @schema actor.schema.json#/$defs/techniqueCount
 */
export interface TechniqueCount {
	id: TechniqueId;
	count: number;
}

/**
 * A CVE named in the actor's reports, with its KEV status.
 * @schema actor.schema.json#/$defs/actorCve
 */
export interface ActorCve {
	cve: CveId;
	kev: boolean;
	/** Null when the CVE is not in KEV. */
	ransomware: boolean | null;
}

/**
 * Dated reports in one quarter. Quarters with no reports are left out.
 * @schema actor.schema.json#/$defs/timelinePoint
 */
export interface TimelinePoint {
	quarter: Quarter;
	count: number;
}

/**
 * A field where published sources disagree. Show every side; pick none.
 * @schema actor.schema.json#/$defs/conflict
 */
export interface Conflict {
	field: ConflictField;
	values: SourcedValue[];
}

/**
 * One actor's profile. Any list may be empty, and the page hides a section
 * with nothing in it.
 * @schema actor.schema.json#
 */
export interface Actor {
	id: ActorId;
	name: string;
	aliases: AliasClaim[];
	origin: SourcedValue[];
	sponsor: SourcedValue[];
	motivation: SourcedValue[];
	claimed_targets: ClaimedTargets;
	malware: MalwareClaim[];
	techniques_documented: TechniqueId[];
	techniques_reported: TechniqueCount[];
	cves: ActorCve[];
	/** Oldest first, with gaps for quarters that have no reports. */
	timeline: TimelinePoint[];
	/** Newest first, undated reports last. */
	reports: ReportId[];
	conflicts: Conflict[];
	evidence_count: number;
}

// ---------------------------------------------------------------------------
// reports/<year>.json and reports/undated.json

/**
 * Metadata for one report. The report itself is never re-hosted.
 * @schema reports_shard.schema.json#/$defs/report
 */
export interface Report {
	id: ReportId;
	title: string;
	/** Null exactly when the report is in reports/undated.json. */
	published: IsoDate | null;
	date_basis: DateBasis;
	organisation: string | null;
	url: string | null;
	/** false: the last link check failed, so show archive_url first. null: not checked yet, or no url. */
	url_ok: boolean | null;
	archive_url: string | null;
	actors: ActorId[];
	actor_names_unresolved: string[];
	cves: CveId[];
	techniques: TechniqueId[];
	sources: SourceKey[];
}

/**
 * One reports shard: a year, or the undated reports.
 * @schema reports_shard.schema.json#
 */
export type ReportsShard = Report[];

// ---------------------------------------------------------------------------
// campaigns.json

/**
 * One named campaign.
 * @schema campaigns.schema.json#/$defs/campaign
 */
export interface Campaign {
	id: CampaignId;
	name: string;
	first_seen: IsoDate | null;
	/** Null while the campaign is ongoing or the source gives no end. */
	last_seen: IsoDate | null;
	actors: ActorId[];
	techniques: TechniqueId[];
	source: SourceKey;
}

/**
 * The whole of campaigns.json.
 * @schema campaigns.schema.json#
 */
export type Campaigns = Campaign[];

// ---------------------------------------------------------------------------
// vulns.json

/**
 * One CVE: every KEV entry, plus every CVE a published report names.
 * @schema vulns.schema.json#/$defs/vuln
 */
export interface Vuln {
	cve: CveId;
	/** Null when the CVE is not in KEV. A report CVE is "KEV" exactly when this is set. */
	kev_date_added: IsoDate | null;
	/** KEV's known-ransomware flag; null when the CVE is not in KEV. */
	ransomware: boolean | null;
	vendor: string | null;
	product: string | null;
	actors: ActorId[];
	report_count: number;
}

/**
 * The whole of vulns.json.
 * @schema vulns.schema.json#
 */
export type Vulns = Vuln[];

// ---------------------------------------------------------------------------
// sources.json

/**
 * One source's health in this build and what the site may publish from it.
 * @schema sources.schema.json#/$defs/source
 */
export interface SourceStatus {
	name: SourceKey;
	/** Null when there has never been a good snapshot. */
	last_success: IsoDate | null;
	record_count: number;
	stale: boolean;
	publish: PublishPolicy;
	/** The licence in short form, such as "CC BY-NC-SA 4.0", or "All rights reserved" when none is named. */
	licence: string;
	/** The licence text, or the terms page SOURCES.md read when the source has no standard licence. */
	licence_url: string;
	/** SOURCES.md's attribution text, character for character. Show it wherever the source is credited. */
	attribution: string;
}

/**
 * The whole of sources.json.
 * @schema sources.schema.json#
 */
export type Sources = SourceStatus[];

// ---------------------------------------------------------------------------
// resolution.json

/**
 * The registry's counts, exactly as Registry.stats() returns them.
 * @schema resolution.schema.json#/$defs/stats
 */
export interface RegistryStats {
	source_record_count: number;
	actor_count: number;
	/** source_record_count minus actor_count. */
	merge_count: number;
	evidence_edge_count: number;
	ambiguity_count: number;
	non_actor_name_count: number;
}

/**
 * The registry measured against the actor names in the paper's data.
 * @schema resolution.schema.json#/$defs/paperMatch
 */
export interface PaperMatch {
	names_total: number;
	resolved: number;
	typed_non_actor: number;
	/** resolved / names_total, between 0 and 1; null when the paper's data is unavailable. */
	match_rate: number | null;
}

/**
 * An alias that names two or more ATT&CK groups, so no merge was made.
 * @schema resolution.schema.json#/$defs/ambiguity
 */
export interface Ambiguity {
	/** The normalized key, such as "winnti". */
	alias: string;
	candidates: ActorId[];
}

/**
 * A report actor name, from a publishable source, that resolved to no actor.
 * @schema resolution.schema.json#/$defs/unresolvedName
 */
export interface UnresolvedName {
	name: string;
	count: number;
	typed_as: SoftwareKind | null;
}

/**
 * The whole of resolution.json, published on the Methodology page.
 * @schema resolution.schema.json#
 */
export interface Resolution {
	stats: RegistryStats;
	paper_match: PaperMatch;
	ambiguities: Ambiguity[];
	/** Most frequent first, at most 200. */
	unresolved_names: UnresolvedName[];
}

// ---------------------------------------------------------------------------
// build.json

/**
 * What wrote this data and when, and which report shards exist.
 * @schema build.schema.json#
 */
export interface Build {
	built_at: IsoDateTime;
	/** The pipeline version. The hand-made sample says "sample" here. */
	version: string;
	/**
	 * Years with a reports/<year>.json shard, ascending. reports/undated.json
	 * always exists and is not listed. A static host cannot list a directory,
	 * so read this rather than guessing which years exist.
	 */
	report_years: number[];
}

// ---------------------------------------------------------------------------
// slugs.json

/**
 * One slug ever published, and what the pipeline needs to recognise its actor.
 * @schema slugs.schema.json#/$defs/slugEntry
 */
export interface SlugEntry {
	/** The actor's ID and URL segment. Frozen once published. */
	slug: ActorId;
	/** The name the page showed in the last build that published the slug. */
	display_name: string;
	/** Published member records as "source:source_id", or an ATT&CK group ID. Sorted. Never alias names. */
	anchors: string[];
	first_published: IsoDate;
	/** The number added because the natural slug was taken, or null when none was needed. */
	suffix: number | null;
	/** True when no published actor owns the slug. A retired slug is never reused. */
	retired: boolean;
	/** The slug of the actor this one was merged into, or null. It ends any chain of merges. */
	merged_into: ActorId | null;
}

/**
 * The whole of slugs.json, sorted by slug.
 * @schema slugs.schema.json#
 */
export interface SlugRegistry {
	entries: SlugEntry[];
}

// ---------------------------------------------------------------------------
// trends.json

/**
 * Reports on one actor in one quarter, with the year-earlier count.
 * @schema trends.schema.json#/$defs/activityRow
 */
export interface ReportingActivityRow {
	actor: ActorId;
	quarter: Quarter;
	count: number;
	/** 0 when there were no reports a year earlier. */
	prev_year_count: number;
}

/**
 * An actor first seen within 365 days of the build.
 * @schema trends.schema.json#/$defs/newActor
 */
export interface NewActor {
	actor: ActorId;
	first_seen: IsoDate;
	/** A source key, or "report" when the earliest dated report set first_seen. */
	basis: string;
}

/**
 * KEV additions in one month.
 * @schema trends.schema.json#/$defs/kevMonth
 */
export interface KevMonth {
	month: Month;
	added: number;
	ransomware: number;
}

/**
 * A KEV CVE named in reports alongside resolved actors.
 * @schema trends.schema.json#/$defs/kevActorLink
 */
export interface KevActorLink {
	cve: CveId;
	actors: ActorId[];
}

/**
 * Techniques in an actor's recent reports compared with what ATT&CK documents.
 * @schema trends.schema.json#/$defs/reportedVsDocumented
 */
export interface ReportedVsDocumented {
	actor: ActorId;
	reported_only: TechniqueId[];
	documented_only_count: number;
	overlap: number;
}

/**
 * The health fields of sources.json, without the publish policy or licence fields.
 * @schema trends.schema.json#/$defs/sourceHealth
 */
export interface SourceHealth {
	name: SourceKey;
	last_success: IsoDate | null;
	record_count: number;
	stale: boolean;
}

/**
 * The counting rule printed under each chart, keyed by its section.
 * @schema trends.schema.json#/$defs/notes
 */
export interface TrendNotes {
	reporting_activity: string;
	new_actors: string;
	kev_monthly: string;
	kev_actor_links: string;
	reported_vs_documented: string;
	source_health: string;
}

/**
 * The whole of trends.json. Every series starts at window_start.
 * @schema trends.schema.json#
 */
export interface Trends {
	window_start: IsoDate;
	generated_at: IsoDateTime;
	reporting_activity: ReportingActivityRow[];
	new_actors: NewActor[];
	kev_monthly: KevMonth[];
	kev_actor_links: KevActorLink[];
	reported_vs_documented: ReportedVsDocumented[];
	source_health: SourceHealth[];
	notes: TrendNotes;
}
