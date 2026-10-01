/**
 * Rows, filters and text search for the explore view.
 *
 * Everything here is pure: it takes data and returns data, touches neither
 * the DOM nor the URL, and so is unit-tested on its own. The page reads the
 * filters from the query string with parseFilters, narrows the rows with
 * applyFilters, and writes changes back with withFilters.
 */
import { indexForm } from '$lib/data/report-id';
import type { ActorsIndex, Campaign, ReportsIndex, SourceKey } from '$lib/data/types';

/**
 * Sources whose rows the site may show only as a title, a date and links.
 * ORKL has not yet answered a request to publish more, so its report
 * metadata beyond those three things stays out of every view.
 */
const LINK_ONLY_ROW_SOURCES: ReadonlySet<SourceKey> = new Set(['orkl']);

/** One line of the explore table: a report or a campaign. */
export interface ExploreRow {
	kind: 'report' | 'campaign';
	/**
	 * A report's id as the index stores it (a digest cut to the index's id
	 * length; see report-id.ts) or a campaign's id.
	 */
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
	/** The part of actors that only the title names. Empty for a campaign. */
	actorsFromTitle: string[];
	sources: SourceKey[];
	cves: string[];
	techniques: string[];
	/** At least one of the row's CVEs is in the KEV catalogue. */
	kev: boolean;
	/** The row may show only its title, date and links. */
	linkOnly: boolean;
	/**
	 * Everything text search looks at, lower case, with each run of
	 * punctuation as one space and a space at the front. See `normalise`.
	 */
	haystack: string;
	/** Set for a campaign row. A report's full record is read from its shard when it is opened. */
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
 * Text as search sees it: lower case, every run of anything that is not a
 * letter or a digit turned into one space, and a space in front. A query word
 * then matches only at the start of a word, which is a plain `includes` of a
 * space and the word. "T1566.002" becomes " t1566 002", so a search for
 * "t1566" and one for "t1566.002" both find it.
 */
export function normalise(text: string): string {
	return ` ${text.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim()}`;
}

/** The CVEs in the KEV catalogue that the index names, for marking them in the panel. */
export function kevCves(index: ReportsIndex): Set<string> {
	return new Set(index.kev.map((p) => index.tables.cves[p]));
}

/**
 * Turn the index and the campaigns into rows, newest first with undated rows
 * last. The index is already in that order, so only the campaigns are sorted
 * and the two lists are merged. Sorting once here means every filtered view
 * is already in order.
 *
 * Every string in a row is one of the index's table entries, shared rather
 * than copied, so thirty thousand rows cost little memory.
 */
export function toRows(index: ReportsIndex, campaigns: Campaign[], actors: ActorsIndex): ExploreRow[] {
	const { tables, columns } = index;
	if (tables.sources.length > 31) throw new Error('The index has more sources than the bit mask can hold');
	const kev = new Set(index.kev);
	const actorText = new Map(actors.map((a) => [a.id, [a.name, ...a.aliases].join(' ')]));
	const textFor = (ids: string[]) => ids.map((id) => actorText.get(id) ?? id).join(' ');
	// An actor is named by many reports, so its text is worked out once.
	const actorAt = tables.actors.map((id) => normalise(textFor([id])));

	const masks = new Map<number, SourceKey[]>();
	const sourcesFor = (mask: number): SourceKey[] => {
		let keys = masks.get(mask);
		if (!keys) {
			keys = tables.sources.filter((_, bit) => mask & (1 << bit));
			masks.set(mask, keys);
		}
		return keys;
	};

	const reports: ExploreRow[] = new Array(index.total);
	for (let i = 0; i < index.total; i++) {
		const id = columns.id[i];
		const sources = sourcesFor(columns.sources[i]);
		const linkOnly = sources.some((s) => LINK_ONLY_ROW_SOURCES.has(s));
		const org = columns.organisation[i];
		const organisation = linkOnly || org == null ? null : tables.organisations[org];
		const cves = columns.cves[i].map((p) => tables.cves[p]);
		const techniques = columns.techniques[i].map((p) => tables.techniques[p]);
		const actorPositions = columns.actors[i];
		reports[i] = {
			kind: 'report',
			id,
			key: `report:${id}`,
			title: columns.title[i],
			date: columns.published[i],
			end: null,
			organisation,
			actors: actorPositions.map((p) => tables.actors[p]),
			actorsFromTitle: columns.actors_from_title[i].map((p) => tables.actors[p]),
			sources,
			cves,
			techniques,
			kev: columns.cves[i].some((p) => kev.has(p)),
			linkOnly,
			haystack:
				normalise([columns.title[i], organisation ?? '', ...cves, ...techniques].join(' ')) +
				actorPositions.map((p) => actorAt[p]).join(''),
			campaign: null
		};
	}

	const camps: ExploreRow[] = campaigns
		.map(
			(c): ExploreRow => ({
				kind: 'campaign',
				id: c.id,
				key: `campaign:${c.id}`,
				title: c.name,
				date: c.first_seen,
				end: c.last_seen,
				organisation: null,
				actors: c.actors,
				actorsFromTitle: [],
				sources: [c.source],
				cves: [],
				techniques: c.techniques,
				kev: false,
				linkOnly: false,
				haystack: normalise([c.name, ...c.techniques].join(' ')) + normalise(textFor(c.actors)),
				campaign: c
			})
		)
		.sort(byDateDesc);

	// A report goes first when a report and a campaign tie.
	const out: ExploreRow[] = [];
	let r = 0;
	let c = 0;
	while (r < reports.length && c < camps.length) {
		out.push(byDateDesc(camps[c], reports[r]) < 0 ? camps[c++] : reports[r++]);
	}
	while (r < reports.length) out.push(reports[r++]);
	while (c < camps.length) out.push(camps[c++]);
	return out;
}

/** Newest first, undated last, then by title. Titles are compared as lower case text, as the pipeline does. */
function byDateDesc(a: ExploreRow, b: ExploreRow): number {
	if (a.date !== b.date) {
		if (a.date == null) return 1;
		if (b.date == null) return -1;
		return a.date < b.date ? 1 : -1;
	}
	const ta = a.title.toLowerCase();
	const tb = b.title.toLowerCase();
	return ta < tb ? -1 : ta > tb ? 1 : 0;
}

/** The sources and publishers to offer in the filter bar, from the rows as they are shown. */
export function facets(rows: ExploreRow[]): { sources: string[]; publishers: string[] } {
	// Taken from the rows, not from the index tables, so the publisher of a
	// link-only row (already removed from its row) never reaches the list.
	const sources = new Set<string>();
	const publishers = new Set<string>();
	for (const r of rows) {
		for (const s of r.sources) sources.add(s);
		if (r.organisation != null) publishers.add(r.organisation);
	}
	const sorted = (set: Set<string>) => [...set].sort((a, b) => a.localeCompare(b, 'en'));
	return { sources: sorted(sources), publishers: sorted(publishers) };
}

/**
 * A finder for the row that `?report=` or `?campaign=` names. A report id in
 * a link may be the short form the page writes, a full id from an actor page,
 * a longer prefix from a link saved under another build, or a shorter prefix
 * from a link saved when fewer characters told reports apart. A shorter
 * prefix finds a report only when it names exactly one, because guessing
 * would open the wrong report.
 */
export function rowLookup(
	rows: ExploreRow[],
	idLen: number
): (kind: 'report' | 'campaign', id: string) => ExploreRow | null {
	const byKey = new Map(rows.map((r) => [r.key, r]));
	return (kind, id) => {
		if (kind === 'campaign') return byKey.get(`campaign:${id}`) ?? null;
		const exact = byKey.get(`report:${indexForm(id, idLen)}`);
		if (exact) return exact;
		if (!/^[0-9a-f]{6,}$/.test(id) || id.length >= idLen) return null;
		let found: ExploreRow | null = null;
		for (const r of rows) {
			if (r.kind !== 'report' || !r.id.startsWith(id)) continue;
			if (found) return null;
			found = r;
		}
		return found;
	};
}

/**
 * The rows that pass every filter, in their original order. An unknown key
 * in `filters` is ignored. A text query needs every word to start a word
 * somewhere in the row's title, publisher, actor names, CVEs or techniques.
 */
export function applyFilters(rows: ExploreRow[], filters: Partial<Filters>): ExploreRow[] {
	const f: Filters = { ...NO_FILTERS, ...pick(filters) };
	const words = normalise(f.q)
		.split(' ')
		.filter(Boolean)
		.map((w) => ` ${w}`);
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
		for (const w of words) if (!r.haystack.includes(w)) return false;
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

/**
 * A copy of `params` with the filter keys replaced by `filters`. Other keys stay, except the
 * page number: a new filter starts again from the first page.
 */
export function withFilters(params: URLSearchParams, filters: Filters): URLSearchParams {
	const next = new URLSearchParams(params);
	next.delete('page');
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
