// The data the explore specs expect, read from the same files the site is
// built from, plus helpers that change the index on its way to the page.
//
// APTX_DATA points a run at a data set that is not committed yet. It is the
// same variable scripts/copy-data.mjs reads, so the site and its tests always
// see the same files.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Build, Report, ReportsIndex, SourceKey } from '../src/lib/data/types';
import { shortId } from '../src/lib/data/report-id';

const dataDir = process.env.APTX_DATA ?? fileURLToPath(new URL('../../data', import.meta.url));

export const read = <T>(path: string): T => JSON.parse(readFileSync(join(dataDir, path), 'utf8')) as T;

export const build = read<Build>('build.json');
export const index = read<ReportsIndex>('reports/index.json');
export const idLen = index.id_len;
export const short = (id: string) => shortId(id, idLen);

/** Every report, read from the year shards as the panel reads them. */
export const reports: Report[] = [
	...build.report_years.flatMap((y) => read<Report[]>(`reports/${y}.json`)),
	...read<Report[]>('reports/undated.json')
];

/** A route pattern for the year shards only. The index sits in the same folder and is not a list of reports. */
export const SHARD = /\/data\/reports\/(\d{4}|undated)\.json(\?|$)/;
/** A route pattern for the index, with or without its version query. */
export const INDEX = /\/data\/reports\/index\.json(\?|$)/;

/** One report as the table needs it, for building an index with extra rows. */
export interface Extra {
	id: string;
	title: string;
	published: string | null;
	organisation?: string | null;
	sources?: SourceKey[];
	actors?: string[];
}

/**
 * The index with extra rows added, still sorted the way the pipeline sorts it
 * (newest first, undated last, then title, then id). The tables grow when an
 * extra names an organisation, source or actor the index does not have yet.
 */
export function withExtraRows(base: ReportsIndex, extras: Extra[], builtAt = base.built_at): ReportsIndex {
	const tables = {
		sources: [...base.tables.sources],
		organisations: [...base.tables.organisations],
		actors: [...base.tables.actors],
		cves: [...base.tables.cves],
		techniques: [...base.tables.techniques]
	};
	const at = <T>(list: T[], value: T) => {
		const i = list.indexOf(value);
		if (i >= 0) return i;
		list.push(value);
		return list.length - 1;
	};
	const c = base.columns;
	const rows = c.id.map((id, i) => ({
		id,
		title: c.title[i],
		published: c.published[i],
		organisation: c.organisation[i],
		sources: c.sources[i],
		actors: c.actors[i],
		cves: c.cves[i],
		techniques: c.techniques[i]
	}));
	for (const e of extras) {
		let mask = 0;
		for (const s of e.sources ?? ['dfir']) mask |= 1 << at(tables.sources, s);
		rows.push({
			id: e.id,
			title: e.title,
			published: e.published,
			organisation: e.organisation ? at(tables.organisations, e.organisation) : null,
			sources: mask,
			actors: (e.actors ?? []).map((a) => at(tables.actors, a)),
			cves: [],
			techniques: []
		});
	}
	rows.sort((a, b) => {
		if (a.published !== b.published) {
			if (a.published == null) return 1;
			if (b.published == null) return -1;
			return a.published < b.published ? 1 : -1;
		}
		const ta = a.title.toLowerCase();
		const tb = b.title.toLowerCase();
		if (ta !== tb) return ta < tb ? -1 : 1;
		return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
	});
	return {
		built_at: builtAt,
		id_len: base.id_len,
		total: rows.length,
		tables,
		kev: base.kev,
		columns: {
			id: rows.map((r) => r.id),
			title: rows.map((r) => r.title),
			published: rows.map((r) => r.published),
			organisation: rows.map((r) => r.organisation),
			sources: rows.map((r) => r.sources),
			actors: rows.map((r) => r.actors),
			cves: rows.map((r) => r.cves),
			techniques: rows.map((r) => r.techniques)
		}
	};
}
