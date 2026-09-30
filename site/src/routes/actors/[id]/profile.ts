/**
 * Pure helpers for the actor profile. The server load and the page share
 * them, and they are unit-tested without a browser.
 */
import type { Actor, DateBasis, Report, ReportId, SourceKey, SourcedValue } from '$lib/data';
import { SOURCE_LABELS } from '$lib/data/labels';
import { describeLinks } from '$lib/links';

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
