/**
 * Pure helpers for the actor profile. The server load and the page share
 * them, and they are unit-tested without a browser.
 */
import type { Actor, DateBasis, Report, ReportId, SourceKey, SourcedValue } from '$lib/data';
import { SOURCE_LABELS } from '$lib/data/labels';

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
	kind: 'original' | 'archive';
}

/**
 * Which link a report's title opens, and which one sits beside it.
 *
 * The original publisher comes first, because the report is theirs. When
 * the last link check found the original dead (url_ok false), the archive
 * leads instead and the page says why. An unchecked link (null) is treated
 * as working: most are, and a false alarm on every new report would teach
 * readers to ignore the warning.
 */
export function reportLinks(r: Pick<Report, 'url' | 'url_ok' | 'archive_url'>): {
	primary: ReportLink | null;
	secondary: ReportLink | null;
	originalFailed: boolean;
} {
	const original: ReportLink | null = r.url ? { href: r.url, kind: 'original' } : null;
	const archive: ReportLink | null = r.archive_url ? { href: r.archive_url, kind: 'archive' } : null;
	const originalFailed = original !== null && r.url_ok === false;
	if (originalFailed && archive) return { primary: archive, secondary: original, originalFailed };
	return { primary: original ?? archive, secondary: original ? archive : null, originalFailed };
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
