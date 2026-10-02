/**
 * Pure helpers for the actor profile. The server load and the page share
 * them, and they are unit-tested without a browser.
 */
import type { Actor, DateBasis, Report, ReportId, SourceKey, SourcedValue } from '$lib/data';
import { SOURCE_LABELS } from '$lib/data/labels';
import { formatCount } from '$lib/format';
import { describeLinks } from '$lib/links';
import { countryName } from '../actors';

/**
 * The report fields the profile shows. Link-only sources allow a title, a
 * publisher, a date and a link, so the list shows nothing more than that;
 * the rest of a report stays in the Explore view's detail panel. Dropping
 * the other fields also keeps the page small for an actor with hundreds of
 * reports, because the load's return value is written into the page.
 */
export type ProfileReport = Pick<
	Report,
	'id' | 'title' | 'published' | 'date_basis' | 'organisation' | 'url' | 'url_ok' | 'archive_url' | 'sources'
>;

/**
 * The actor's reports in the order the actor file lists them (newest first,
 * undated last). An ID that no shard holds is returned in `missing` rather
 * than dropped without a trace, so the build can say so.
 */
export function pickReports(
	ids: readonly ReportId[],
	byId: ReadonlyMap<ReportId, Report>
): { reports: ProfileReport[]; missing: ReportId[] } {
	const reports: ProfileReport[] = [];
	const missing: ReportId[] = [];
	for (const id of ids) {
		const r = byId.get(id);
		if (!r) {
			missing.push(id);
			continue;
		}
		reports.push({
			id: r.id,
			title: r.title,
			published: r.published,
			date_basis: r.date_basis,
			organisation: r.organisation,
			url: r.url,
			url_ok: r.url_ok,
			archive_url: r.archive_url,
			sources: r.sources
		});
	}
	return { reports, missing };
}

export interface ReportLink {
	href: string;
	/** What the link is, decided from its host by the same helper as the Explore panel. */
	kind: 'original' | 'copy' | 'unconfirmed';
	label: string;
}

export interface ProfileLinks {
	primary: ReportLink | null;
	secondary: ReportLink | null;
	/** The link that failed its last check, if it was one of the two shown. */
	failed: ReportLink | null;
}

/**
 * Which link a report's title opens, and which one sits beside it.
 *
 * The role and label of each link come from its host through describeLinks,
 * so a mirror stored in the url field is never shown as the original. The
 * original comes first, because the report is theirs. When the last link
 * check found a link dead (url_ok false), it moves behind the other one and
 * the page says which failed. An unchecked link (null) is treated as
 * working: most are, and a false alarm on every new report would teach
 * readers to ignore the warning.
 */
export function reportLinks(r: Pick<Report, 'url' | 'url_ok' | 'archive_url'>): ProfileLinks {
	const shown = describeLinks(r).links.map((l) => ({
		link: { href: l.href, kind: l.role, label: l.class.label } satisfies ReportLink,
		unreachable: l.unreachable
	}));
	return {
		primary: shown[0]?.link ?? null,
		secondary: shown[1]?.link ?? null,
		failed: shown.find((l) => l.unreachable)?.link ?? null
	};
}

/**
 * The one sentence under a report that warns about its links, or null when
 * the title opens the publisher's page and nothing failed. A failed link is
 * reported first, because it changes what the reader can open.
 */
export function linkNote(links: ProfileLinks): string | null {
	const { primary, failed } = links;
	if (failed) {
		return failed.kind === 'original'
			? 'The original link failed its last check.'
			: `The link to ${failed.label} failed its last check.`;
	}
	if (primary?.kind === 'copy') return `The title opens ${primary.label}, not the publisher’s page.`;
	if (primary?.kind === 'unconfirmed') return 'The title opens a link whose publisher is not confirmed.';
	return null;
}

/**
 * One entry per distinct value, carrying every source that asserts it.
 * Two sources agreeing on "KP" is one fact with two badges; showing it
 * twice would read like a disagreement.
 */
export function groupValues(values: readonly SourcedValue[]): { value: string; sources: SourceKey[] }[] {
	const out = new Map<string, SourceKey[]>();
	for (const { value, source } of values) {
		const sources = out.get(value) ?? [];
		if (!sources.includes(source)) sources.push(source);
		out.set(value, sources);
	}
	return [...out].map(([value, sources]) => ({ value, sources }));
}

const SOURCE_ORDER = Object.keys(SOURCE_LABELS);

/** Every source behind a published field of the actor, in the order About lists them. */
export function actorSources(actor: Actor): SourceKey[] {
	const seen = new Set<SourceKey>();
	for (const a of actor.aliases) for (const s of a.sources) seen.add(s);
	for (const v of [
		...actor.origin,
		...actor.sponsor,
		...actor.motivation,
		...actor.claimed_targets.countries,
		...actor.claimed_targets.sectors
	])
		seen.add(v.source);
	for (const m of actor.malware) seen.add(m.source);
	// A source added to the pipeline before the site has a label for it still
	// has to be credited, so it sorts last instead of disappearing.
	const rank = (s: SourceKey) => {
		const i = SOURCE_ORDER.indexOf(s);
		return i < 0 ? SOURCE_ORDER.length : i;
	};
	return [...seen].sort((a, b) => rank(a) - rank(b));
}

/** Reports the timeline cannot place because they have no usable date. */
export function undatedCount(actor: Actor): number {
	const dated = actor.timeline.reduce((sum, p) => sum + p.count, 0);
	return Math.max(0, actor.reports.length - dated);
}

/**
 * Where each report's date came from, as the report list prints it next to
 * the date. The Methodology page explains the order these are tried in.
 */
export const DATE_BASIS_LABELS: Readonly<Record<DateBasis, string>> = {
	'malpedia-library': 'Malpedia library date',
	'title-date': 'date in the title',
	'file-metadata': 'file creation date',
	'orkl-ingest': 'date ORKL added it',
	publisher: "publisher's date",
	paper: "date in the CCS '25 data",
	unknown: 'no usable date'
};

/** "T1059.001" to its page on attack.mitre.org. */
export function techniqueUrl(id: string): string {
	return `https://attack.mitre.org/techniques/${id.replace('.', '/')}/`;
}

/** How many items each long list shows before its "Show all" control. */
export const FIRST_REPORTS = 10;
export const FIRST_ALIASES = 14;
export const FIRST_TECHNIQUES = 10;
export const FIRST_CHIPS = 12;

/** The four sources that name actors, each with the two-letter code its box carries. */
export const NAME_SOURCES = [
	{ key: 'attack', code: 'AT' },
	{ key: 'misp', code: 'MI' },
	{ key: 'etda', code: 'ET' },
	{ key: 'malpedia', code: 'MA' }
] as const satisfies readonly { key: SourceKey; code: string }[];

/** Sources on an alias that have no box of their own. They still get a badge. */
export function otherSources(sources: readonly SourceKey[]): SourceKey[] {
	return sources.filter((s) => !NAME_SOURCES.some((n) => n.key === s));
}

const NUMBER_WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine'];

/** Numbers under ten as words and the rest as numerals, for running text. */
export function countWord(n: number): string {
	return n >= 0 && n < 10 ? NUMBER_WORDS[n] : formatCount(n);
}

const NAMES_IN_LEDE = 5;

/**
 * The sentence or two under the actor's name, built only from the data: a few
 * of its other names, and how many sources agree on an origin. Null when
 * there is nothing to say, so the page shows no empty line. An actor that only
 * a vendor's cluster ID stands behind says so instead.
 */
export function ledeFor(actor: Pick<Actor, 'name' | 'aliases' | 'origin' | 'cluster_only'>): string | null {
	if (actor.cluster_only) {
		const source = actor.aliases[0]?.sources[0];
		const vendor = source ? SOURCE_LABELS[source]?.name ?? source : 'A vendor';
		return `Unconfirmed vendor cluster. ${vendor} used this ID in a post title, and no source lists it as an actor yet.`;
	}
	const parts: string[] = [];
	const others = actor.aliases.map((a) => a.value).filter((v) => v !== actor.name);
	if (others.length > 0) {
		const shown = others.slice(0, NAMES_IN_LEDE);
		const rest = others.length - shown.length;
		if (rest > 0) shown.push(`${formatCount(rest)} other ${rest === 1 ? 'name' : 'names'}`);
		const list = shown.length === 1 ? shown[0] : `${shown.slice(0, -1).join(', ')} and ${shown[shown.length - 1]}`;
		parts.push(`Also reported as ${list}.`);
	}
	const origins = groupValues(actor.origin);
	if (origins.length === 1) {
		const n = origins[0].sources.length;
		parts.push(`Linked to ${countryName(origins[0].value)} by ${countWord(n)} ${n === 1 ? 'source' : 'sources'}.`);
	} else if (origins.length > 1) {
		parts.push('Sources disagree on the origin.');
	}
	return parts.length > 0 ? parts.join(' ') : null;
}

/** ATT&CK techniques that no recent report names, so the table of recent techniques leaves them out. */
export function documentedOnly(actor: Pick<Actor, 'techniques_documented' | 'techniques_reported'>): string[] {
	const seen = new Set(actor.techniques_reported.map((t) => t.id));
	return actor.techniques_documented.filter((id) => !seen.has(id));
}
