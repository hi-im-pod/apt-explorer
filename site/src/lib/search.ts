/**
 * Rows, filters and text search for the explore view.
 *
 * Everything here is pure: it takes data and returns data, touches neither
 * the DOM nor the URL, and so is unit-tested on its own. The page reads the
 * filters from the query string with parseFilters, narrows the rows with
 * applyFilters, and writes changes back with withFilters.
 */
import MiniSearch from 'minisearch';
import type { ActorsIndex, Campaign, Report, SourceKey, Vuln } from '$lib/data/types';

/**
 * Sources whose rows the site may show only as a title, a date and links.
 * ORKL has not yet answered a request to publish more, so its report
 * metadata beyond those three things stays out of every view.
 */
const LINK_ONLY_ROW_SOURCES: ReadonlySet<SourceKey> = new Set(['orkl']);

/** One line of the explore table: a report or a campaign. */
export interface ExploreRow {
	kind: 'report' | 'campaign';
	id: string;
	/** kind and id together. A report and a campaign may share an ID. */
	key: string;
	title: string;
	/** A report's publication date or a campaign's first sighting; null when unknown. */
	date: string | null;
	/** A campaign's last sighting. Null for a report, or for a campaign with no end yet. */
	end: string | null;
	/** Null for a link-only row, whatever the data says. */
	organisation: string | null;
	actors: string[];
	/** Names the registry could not resolve. Always empty for a link-only row. */
	unresolved: string[];
	sources: SourceKey[];
	cves: string[];
	techniques: string[];
	/** At least one of the row's CVEs is in the KEV catalogue. */
	kev: boolean;
	/** The row may show only its title, date and links. */
	linkOnly: boolean;
	/** Actor names and aliases, for text search. */
	actorText: string;
	report: Report | null;
	campaign: Campaign | null;
}

/** The filters the explore view keeps in its query string. */
export interface Filters {
	q: string;
	from: string | null;
	to: string | null;
	actor: string | null;
	source: string | null;
	org: string | null;
	cve: string | null;
	kev: boolean;
	tech: string | null;
	undated: boolean;
}

export const NO_FILTERS: Readonly<Filters> = {
	q: '',
	from: null,
	to: null,
	actor: null,
	source: null,
	org: null,
	cve: null,
	kev: false,
	tech: null,
	undated: false
};

/** The query-string keys, in the order they are written back. */
const FILTER_KEYS = Object.keys(NO_FILTERS) as (keyof Filters)[];
const TEXT_KEYS = ['actor', 'source', 'org', 'cve', 'tech'] as const;
const DATE_KEYS = ['from', 'to'] as const;
const FLAG_KEYS = ['kev', 'undated'] as const;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Join reports and campaigns with the KEV list and the actor names, then
 * sort newest first with undated rows last. Sorting once here means every
 * filtered view is already in order.
 */
export function toRows(
	reports: Report[],
	campaigns: Campaign[],
	vulns: Vuln[],
	actors: ActorsIndex
): ExploreRow[] {
	const kevCves = new Set(vulns.filter((v) => v.kev_date_added != null).map((v) => v.cve));
	const actorText = new Map(actors.map((a) => [a.id, [a.name, ...a.aliases].join(' ')]));
	const textFor = (ids: string[]) => ids.map((id) => actorText.get(id) ?? id).join(' ');

	const rows: ExploreRow[] = [];
	for (const r of reports) {
		const linkOnly = r.sources.some((s) => LINK_ONLY_ROW_SOURCES.has(s));
		rows.push({
			kind: 'report',
			id: r.id,
			key: `report:${r.id}`,
			title: r.title,
			date: r.published,
			end: null,
			organisation: linkOnly ? null : r.organisation,
			actors: r.actors,
			unresolved: linkOnly ? [] : r.actor_names_unresolved,
			sources: r.sources,
			cves: r.cves,
			techniques: r.techniques,
			kev: r.cves.some((c) => kevCves.has(c)),
			linkOnly,
			actorText: textFor(r.actors),
			report: r,
			campaign: null
		});
	}
	for (const c of campaigns) {
		rows.push({
			kind: 'campaign',
			id: c.id,
			key: `campaign:${c.id}`,
			title: c.name,
			date: c.first_seen,
			end: c.last_seen,
			organisation: null,
			actors: c.actors,
			unresolved: [],
			sources: [c.source],
			cves: [],
			techniques: c.techniques,
			kev: false,
			linkOnly: false,
			actorText: textFor(c.actors),
			report: null,
			campaign: c
		});
	}
	return rows.sort(byDateDesc);
}

function byDateDesc(a: ExploreRow, b: ExploreRow): number {
	if (a.date !== b.date) {
		if (a.date == null) return 1;
		if (b.date == null) return -1;
		return a.date < b.date ? 1 : -1;
	}
	return a.title.localeCompare(b.title, 'en');
}

/** A MiniSearch index over the rows' titles, publishers, actor names, CVEs and techniques. */
export function buildIndex(rows: ExploreRow[]): MiniSearch<ExploreRow> {
	const index = new MiniSearch<ExploreRow>({
		idField: 'key',
		fields: ['title', 'organisation', 'actorText', 'cveText', 'techText'],
		extractField: (row, field) => {
			if (field === 'cveText') return row.cves.join(' ');
			if (field === 'techText') return row.techniques.join(' ');
			const value = row[field as keyof ExploreRow];
			return typeof value === 'string' ? value : '';
		},
		searchOptions: {
			// Every word must match, so adding a word narrows the list the way
			// the other filters do.
			combineWith: 'AND',
			prefix: true,
			fuzzy: (term) => (term.length > 5 ? 0.15 : 0),
			boost: { title: 2 }
		}
	});
	index.addAll(rows);
	return index;
}

/**
 * The rows that pass every filter, in their original order. An unknown key
 * in `filters` is ignored. With a text query and no index, the query is
 * matched against titles only.
 */
export function applyFilters(
	rows: ExploreRow[],
	filters: Partial<Filters>,
	index?: MiniSearch<ExploreRow>
): ExploreRow[] {
	const f: Filters = { ...NO_FILTERS, ...pick(filters) };
	const q = f.q.trim();
	let hits: Set<string> | null = null;
	if (q && index) hits = new Set(index.search(q).map((h) => String(h.id)));
	const needle = q.toLowerCase();
	const cve = f.cve?.trim().toUpperCase() || null;
	const tech = f.tech?.trim().toUpperCase() || null;

	return rows.filter((r) => {
		if (r.date == null) {
			if (!f.undated) return false;
		} else {
			// A campaign is in range when its span overlaps the range. One with
			// no last sighting may still be running, so no start date excludes it.
			const last = r.kind === 'campaign' ? r.end : r.date;
			if (f.from && last != null && last < f.from) return false;
			if (f.to && r.date > f.to) return false;
		}
		if (f.actor && !r.actors.includes(f.actor)) return false;
		if (f.source && !r.sources.includes(f.source)) return false;
		if (f.org && r.organisation !== f.org) return false;
		if (f.kev && !r.kev) return false;
		if (cve && !r.cves.some((c) => c.startsWith(cve))) return false;
		// "T1566" also finds its sub-techniques, "T1566.001" and so on.
		if (tech && !r.techniques.some((t) => t.startsWith(tech))) return false;
		if (hits) return hits.has(r.key);
		if (needle) return r.title.toLowerCase().includes(needle);
		return true;
	});
}

/** Only the known filter keys, so a stray key cannot reach the filter logic. */
function pick(filters: Partial<Filters>): Partial<Filters> {
	const out: Partial<Filters> = {};
	for (const key of FILTER_KEYS) {
		if (key in filters) Object.assign(out, { [key]: filters[key] });
	}
	return out;
}

/** The filters in a query string. A malformed date is dropped rather than guessed at. */
export function parseFilters(params: URLSearchParams): Filters {
	const f: Filters = { ...NO_FILTERS, q: params.get('q') ?? '' };
	for (const key of TEXT_KEYS) f[key] = params.get(key)?.trim() || null;
	for (const key of DATE_KEYS) {
		const value = params.get(key);
		f[key] = value && ISO_DATE.test(value) ? value : null;
	}
	for (const key of FLAG_KEYS) f[key] = params.get(key) === '1';
	return f;
}

/** A copy of `params` with the filter keys replaced by `filters`. Other keys stay. */
export function withFilters(params: URLSearchParams, filters: Filters): URLSearchParams {
	const next = new URLSearchParams(params);
	for (const key of FILTER_KEYS) next.delete(key);
	for (const key of FILTER_KEYS) {
		const value = filters[key];
		if (typeof value === 'boolean') {
			if (value) next.set(key, '1');
		} else if (value) {
			next.set(key, value);
		}
	}
	return next;
}

/** A copy of `params` with at most one open detail: a report or a campaign. */
export function withSelection(
	params: URLSearchParams,
	selection: { report?: string; campaign?: string }
): URLSearchParams {
	const next = new URLSearchParams(params);
	next.delete('report');
	next.delete('campaign');
	if (selection.report) next.set('report', selection.report);
	else if (selection.campaign) next.set('campaign', selection.campaign);
	return next;
}
