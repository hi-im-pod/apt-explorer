import { describe, expect, it } from 'vitest';
import type { ActorsIndex, Campaign, ReportsIndex } from '$lib/data/types';
import {
	applyFilters,
	facets,
	kevCves,
	normalise,
	parseFilters,
	rowLookup,
	toRows,
	withFilters,
	withSelection,
	type ExploreRow
} from './search';

/** The fields of a report that the index keeps. Small hand-made inputs, so each case states what it depends on. */
interface Rep {
	id: string;
	title: string;
	published: string | null;
	organisation: string | null;
	actors: string[];
	cves: string[];
	techniques: string[];
	sources: string[];
}

function report(over: Partial<Rep> & Pick<Rep, 'id'>): Rep {
	return {
		title: `Report ${over.id}`,
		published: '2024-05-01',
		organisation: 'Harbor CERT',
		actors: [],
		cves: [],
		techniques: [],
		sources: ['dfir'],
		...over
	};
}

/**
 * The index the pipeline would write for `reps`. Tables here are in order of
 * first use rather than by frequency, which the page does not depend on.
 */
function makeIndex(reps: Rep[], kev: string[] = [], idLen = 8): ReportsIndex {
	const sorted = [...reps].sort((a, b) => {
		if (a.published !== b.published) {
			if (a.published == null) return 1;
			if (b.published == null) return -1;
			return a.published < b.published ? 1 : -1;
		}
		const ta = a.title.toLowerCase();
		const tb = b.title.toLowerCase();
		return ta < tb ? -1 : ta > tb ? 1 : a.id < b.id ? -1 : 1;
	});
	const table = (values: (string | null)[]) => [...new Set(values.filter((v): v is string => v != null))];
	const tables = {
		sources: table(sorted.flatMap((r) => r.sources)),
		organisations: table(sorted.map((r) => r.organisation)),
		actors: table(sorted.flatMap((r) => r.actors)),
		cves: table(sorted.flatMap((r) => r.cves)),
		techniques: table(sorted.flatMap((r) => r.techniques))
	};
	const at = (name: keyof typeof tables, v: string) => tables[name].indexOf(v);
	return {
		built_at: '2026-09-28T03:21:05Z',
		id_len: idLen,
		total: sorted.length,
		tables,
		kev: kev.map((c) => at('cves', c)).sort((a, b) => a - b),
		columns: {
			id: sorted.map((r) => (/^[0-9a-f]{40}$/.test(r.id) ? r.id.slice(0, idLen) : r.id)),
			title: sorted.map((r) => r.title),
			published: sorted.map((r) => r.published),
			organisation: sorted.map((r) => (r.organisation == null ? null : at('organisations', r.organisation))),
			sources: sorted.map((r) => r.sources.reduce((m, s) => m + 2 ** at('sources', s), 0)),
			actors: sorted.map((r) => r.actors.map((a) => at('actors', a))),
			cves: sorted.map((r) => r.cves.map((c) => at('cves', c))),
			techniques: sorted.map((r) => r.techniques.map((t) => at('techniques', t)))
		}
	} as ReportsIndex;
}

function campaign(over: Partial<Campaign> & Pick<Campaign, 'id'>): Campaign {
	return {
		name: `Campaign ${over.id}`,
		first_seen: '2019-09-01',
		last_seen: '2020-08-01',
		actors: [],
		techniques: [],
		source: 'attack',
		...over
	};
}

const actors: ActorsIndex = [
	{
		id: 'G0007',
		name: 'APT28',
		aliases: ['APT28', 'Fancy Bear', 'Sofacy'],
		origin: ['RU'],
		report_count: 3,
		last_reported: '2024-02-21',
		sources: ['attack']
	},
	{
		id: 'G0032',
		name: 'Lazarus Group',
		aliases: ['Lazarus Group', 'HIDDEN COBRA'],
		origin: ['KP'],
		report_count: 1,
		last_reported: '2024-04-03',
		sources: ['attack']
	}
];

const reps: Rep[] = [
	report({ id: 'r-2023', published: '2023-11-02', actors: ['G0007'] }),
	report({ id: 'r-2024-apt28', published: '2024-02-21', actors: ['G0007'], cves: ['CVE-2023-23397'] }),
	report({
		id: 'r-2024-lazarus',
		published: '2024-04-03',
		actors: ['G0032'],
		cves: ['CVE-2021-44228'],
		techniques: ['T1566.002'],
		title: 'Log4Shell remains an entry point',
		organisation: 'Blue Meridian Labs'
	}),
	report({ id: 'r-2024-other-cve', published: '2024-06-01', cves: ['CVE-2026-100123'] }),
	report({ id: 'r-undated', published: null })
];

const campaigns: Campaign[] = [
	campaign({ id: 'C0022', name: 'Operation Dream Job', actors: ['G0032'], techniques: ['T1566.002'] }),
	campaign({ id: 'C9999', name: 'Still going', first_seen: '2023-06-01', last_seen: null, actors: ['G0007'] })
];

const index = makeIndex(reps, ['CVE-2023-23397', 'CVE-2021-44228']);
const rows = toRows(index, campaigns, actors);
const ids = (rs: ExploreRow[]) => rs.map((r) => r.id);

describe('toRows', () => {
	it('puts reports and campaigns in one list, newest first, undated last', () => {
		expect(ids(rows)).toEqual([
			'r-2024-other-cve',
			'r-2024-lazarus',
			'r-2024-apt28',
			'r-2023',
			'C9999',
			'C0022',
			'r-undated'
		]);
		expect(rows.find((r) => r.id === 'C0022')?.kind).toBe('campaign');
	});

	it('lists a report and a campaign of the same day by title', () => {
		const same = toRows(
			makeIndex([report({ id: 'r-b', title: 'Bravo', published: '2024-01-01' })]),
			[
				campaign({ id: 'C1', name: 'Alpha', first_seen: '2024-01-01' }),
				campaign({ id: 'C2', name: 'Charlie', first_seen: '2024-01-01' })
			],
			[]
		);
		expect(same.map((r) => r.title)).toEqual(['Alpha', 'Bravo', 'Charlie']);
	});

	it('reads a row from the index: names for actors, keys for sources, CVEs and techniques', () => {
		const lazarus = rows.find((r) => r.id === 'r-2024-lazarus')!;
		expect(lazarus).toMatchObject({
			kind: 'report',
			key: 'report:r-2024-lazarus',
			title: 'Log4Shell remains an entry point',
			date: '2024-04-03',
			end: null,
			organisation: 'Blue Meridian Labs',
			actors: ['G0032'],
			sources: ['dfir'],
			cves: ['CVE-2021-44228'],
			techniques: ['T1566.002'],
			linkOnly: false,
			campaign: null
		});
		// The full report is read only when the panel opens, so a row has no copy of it.
		expect(lazarus).not.toHaveProperty('report');
	});

	it('marks a row KEV only when one of its CVEs is in the catalogue', () => {
		const kev = Object.fromEntries(rows.map((r) => [r.id, r.kev]));
		expect(kev['r-2024-apt28']).toBe(true);
		expect(kev['r-2024-other-cve']).toBe(false);
		expect(kev['C0022']).toBe(false);
	});

	it('lists the KEV CVEs by name, for the panel', () => {
		expect([...kevCves(index)].sort()).toEqual(['CVE-2021-44228', 'CVE-2023-23397']);
	});

	it('drops the publisher of an ORKL row, which is link-only', () => {
		// ORKL's terms are pending, so the site shows only a report's title,
		// date and links. Clearing the field here means no table cell, filter
		// or search result can reveal it either.
		const [orkl] = toRows(
			makeIndex([report({ id: 'orkl-1', sources: ['orkl'], organisation: 'Northwind Threat Research' })]),
			[],
			actors
		);
		expect(orkl.linkOnly).toBe(true);
		expect(orkl.organisation).toBeNull();
		expect(applyFilters([orkl], { q: 'northwind' })).toEqual([]);
		expect(applyFilters([orkl], { org: 'Northwind Threat Research' })).toEqual([]);
	});

	it('reads a row with several sources from the bit mask', () => {
		const [multi] = toRows(makeIndex([report({ id: 'r-m', sources: ['dfir', 'orkl', 'attack'] })]), [], []);
		expect([...multi.sources].sort()).toEqual(['attack', 'dfir', 'orkl']);
		expect(multi.linkOnly).toBe(true);
	});
});

describe('facets', () => {
	it('lists sources and publishers, and leaves out the publisher of a link-only row', () => {
		const all = toRows(
			makeIndex([
				report({ id: 'r-1', organisation: 'Harbor CERT', sources: ['dfir'] }),
				report({ id: 'r-2', organisation: 'Northwind Threat Research', sources: ['orkl'] })
			]),
			[campaign({ id: 'C1' })],
			[]
		);
		expect(facets(all)).toEqual({ sources: ['attack', 'dfir', 'orkl'], publishers: ['Harbor CERT'] });
	});
});

describe('applyFilters', () => {
	it('keeps only dated rows for the actor from the given date', () => {
		const out = applyFilters(rows, { actor: 'G0007', from: '2024-01-01' });
		expect(ids(out)).toEqual(['r-2024-apt28', 'C9999']);
		for (const r of out) {
			expect(r.actors).toContain('G0007');
			expect(r.date).not.toBeNull();
		}
	});

	it('keeps a campaign whose span overlaps the range, including an ongoing one', () => {
		expect(ids(applyFilters(rows, { from: '2020-01-01', to: '2020-12-31' }))).toEqual(['C0022']);
		expect(ids(applyFilters(rows, { from: '2026-01-01' }))).toEqual(['C9999']);
	});

	it('with kev on, keeps rows that name at least one KEV CVE', () => {
		expect(ids(applyFilters(rows, { kev: true }))).toEqual(['r-2024-lazarus', 'r-2024-apt28']);
	});

	it('ignores a key it does not know', () => {
		const unknown = { nonsense: 'G0007' } as unknown as Parameters<typeof applyFilters>[1];
		expect(ids(applyFilters(rows, unknown))).toEqual(ids(applyFilters(rows, {})));
	});

	it('hides undated rows unless asked for them', () => {
		expect(ids(applyFilters(rows, {}))).not.toContain('r-undated');
		expect(ids(applyFilters(rows, { undated: true }))).toContain('r-undated');
		// A date range cannot place an undated report, so the switch alone decides.
		expect(ids(applyFilters(rows, { undated: true, from: '2024-01-01', actor: 'G0007' }))).toEqual([
			'r-2024-apt28',
			'C9999'
		]);
		expect(ids(applyFilters(rows, { undated: true, from: '2024-01-01' }))).toContain('r-undated');
	});

	it('matches a technique with its sub-techniques, and a CVE by prefix, in any case', () => {
		expect(ids(applyFilters(rows, { tech: 't1566' }))).toEqual(['r-2024-lazarus', 'C0022']);
		expect(ids(applyFilters(rows, { cve: 'cve-2023' }))).toEqual(['r-2024-apt28']);
	});

	it('filters by source and by publisher', () => {
		expect(ids(applyFilters(rows, { source: 'attack' }))).toEqual(['C9999', 'C0022']);
		expect(ids(applyFilters(rows, { org: 'Blue Meridian Labs' }))).toEqual(['r-2024-lazarus']);
	});

	it('keeps a report and a campaign apart when they share an ID', () => {
		const clash = toRows(
			makeIndex([report({ id: 'dfir:x', title: 'Alpha' })]),
			[campaign({ id: 'dfir:x', name: 'Beta', source: 'dfir', first_seen: '2024-01-01' })],
			[]
		);
		expect(applyFilters(clash, { q: 'beta' }).map((r) => r.kind)).toEqual(['campaign']);
		expect(new Set(clash.map((r) => r.key)).size).toBe(2);
	});
});

describe('text search', () => {
	it('searches titles, publishers and actor aliases', () => {
		expect(ids(applyFilters(rows, { q: 'fancy bear' }))).toEqual(['r-2024-apt28', 'r-2023', 'C9999']);
		expect(ids(applyFilters(rows, { q: 'log4shell' }))).toEqual(['r-2024-lazarus']);
		expect(ids(applyFilters(rows, { q: 'dream' }))).toEqual(['C0022']);
		expect(ids(applyFilters(rows, { q: 'blue meridian' }))).toEqual(['r-2024-lazarus']);
	});

	it('finds a CVE and a technique by text, with or without the punctuation', () => {
		expect(ids(applyFilters(rows, { q: 'CVE-2023-23397' }))).toEqual(['r-2024-apt28']);
		expect(ids(applyFilters(rows, { q: 't1566.002' }))).toEqual(['r-2024-lazarus', 'C0022']);
		expect(ids(applyFilters(rows, { q: 't1566' }))).toEqual(['r-2024-lazarus', 'C0022']);
	});

	it('is not case sensitive and matches the start of a word', () => {
		expect(ids(applyFilters(rows, { q: 'LOG4' }))).toEqual(['r-2024-lazarus']);
		expect(ids(applyFilters(rows, { q: 'lazar' }))).toEqual(['r-2024-lazarus', 'C0022']);
	});

	it('does not match the middle of a word', () => {
		// "ear" is inside "Bear" and "Meridian" has no such start, so a stray
		// fragment does not flood the table.
		expect(ids(applyFilters(rows, { q: 'ear' }))).toEqual([]);
		expect(ids(applyFilters(rows, { q: 'idian' }))).toEqual([]);
	});

	it('needs every word, so a second word narrows the list', () => {
		expect(ids(applyFilters(rows, { q: 'fancy bear cve-2023' }))).toEqual(['r-2024-apt28']);
		expect(ids(applyFilters(rows, { q: 'fancy zebra' }))).toEqual([]);
	});

	it('ignores extra spaces and punctuation in the query', () => {
		expect(ids(applyFilters(rows, { q: '  log4shell,  ' }))).toEqual(['r-2024-lazarus']);
		expect(ids(applyFilters(rows, { q: '   ' }))).toEqual(ids(applyFilters(rows, {})));
	});

	it('normalises text the same way for rows and queries', () => {
		expect(normalise('Log4Shell: T1566.002 / Café')).toBe(' log4shell t1566 002 café');
	});

	it('combines with the other filters', () => {
		expect(ids(applyFilters(rows, { q: 'fancy', from: '2024-01-01' }))).toEqual(['r-2024-apt28', 'C9999']);
	});
});

describe('rowLookup', () => {
	const A = 'ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12';
	const B = 'ab12cd99ef56ab12cd34ef56ab12cd34ef56ab12';
	const sha = toRows(
		makeIndex([report({ id: A, title: 'A' }), report({ id: B, title: 'B' }), report({ id: 'paper:2025-x', title: 'P' })]),
		[campaign({ id: 'C0022' })],
		[]
	);
	const find = rowLookup(sha, 8);

	it('finds a report by the short id the page writes', () => {
		expect(find('report', 'ab12cd34')?.title).toBe('A');
	});

	it('finds a report by the full id, as actor pages link it', () => {
		expect(find('report', A)?.title).toBe('A');
		expect(find('report', B)?.title).toBe('B');
	});

	it('finds a report by a longer prefix from a link saved under another build', () => {
		expect(find('report', A.slice(0, 12))?.title).toBe('A');
	});

	it('finds a report by a shorter prefix only when it names one report', () => {
		expect(find('report', 'ab12cd3')?.title).toBe('A');
		expect(find('report', 'ab12cd')).toBeNull();
		expect(find('report', 'ab12c')).toBeNull();
	});

	it('finds an id that is not a digest, whole', () => {
		expect(find('report', 'paper:2025-x')?.title).toBe('P');
	});

	it('finds a campaign by id, and does not take a campaign for a report', () => {
		expect(find('campaign', 'C0022')?.kind).toBe('campaign');
		expect(find('report', 'C0022')).toBeNull();
		expect(find('campaign', 'ab12cd34')).toBeNull();
	});

	it('returns null for an id that is not there', () => {
		expect(find('report', 'ffffffff')).toBeNull();
	});
});

describe('speed on a full build', () => {
	// The budget is 100 ms for a filter or a search on 30,000 reports. The
	// rows here are made up but shaped like the real ones: a title of a dozen
	// words, a publisher, and a few actors, CVEs and techniques.
	const words = ['phishing', 'loader', 'ransomware', 'campaign', 'backdoor', 'espionage', 'targets', 'exploit', 'supply', 'chain', 'group', 'malware', 'analysis', 'report', 'zero', 'day'];
	const N = 30_000;
	const big: Rep[] = Array.from({ length: N }, (_, i) =>
		report({
			id: `r-${i}`,
			title: Array.from({ length: 12 }, (_, k) => words[(i * 7 + k * 3) % words.length] + (k === 0 ? ` ${i}` : '')).join(' '),
			published: `20${String(10 + (i % 15))}-0${1 + (i % 9)}-1${i % 9}`,
			organisation: `Publisher ${i % 400}`,
			actors: i % 3 ? ['G0007'] : [],
			cves: i % 5 === 0 ? [`CVE-2023-${1000 + (i % 900)}`] : [],
			techniques: i % 4 === 0 ? ['T1566.002', 'T1059.001'] : []
		})
	);
	const bigIndex = makeIndex(big);

	it('builds the rows quickly', () => {
		const t0 = performance.now();
		const built = toRows(bigIndex, [], actors);
		const ms = performance.now() - t0;
		expect(built).toHaveLength(N);
		// Not a budget in the brief, but the first row cannot show before this is done.
		expect(ms).toBeLessThan(1000);
	});

	it('filters and searches in under 100 ms', () => {
		const built = toRows(bigIndex, [], actors);
		for (const filters of [{ q: 'phishing' }, { q: 'apt28 loader' }, { q: 'zzz' }, { source: 'dfir', kev: true }, { actor: 'G0007', from: '2015-01-01' }]) {
			const t0 = performance.now();
			applyFilters(built, filters);
			const ms = performance.now() - t0;
			expect(ms, JSON.stringify(filters)).toBeLessThan(100);
		}
	});
});

describe('URL state', () => {
	it('reads every filter from the query string and ignores the rest', () => {
		const f = parseFilters(
			new URLSearchParams('q=bear&from=2024-01-01&to=bad&actor=G0007&kev=1&undated=0&x=1&tech=T1566')
		);
		expect(f).toEqual({
			q: 'bear',
			from: '2024-01-01',
			to: null,
			actor: 'G0007',
			source: null,
			org: null,
			cve: null,
			kev: true,
			tech: 'T1566',
			undated: false
		});
	});

	it('writes filters back without touching the open report', () => {
		const params = new URLSearchParams('actor=G0007&report=abc');
		const next = withFilters(params, { ...parseFilters(params), actor: null, kev: true });
		expect(next.toString()).toBe('report=abc&kev=1');
	});

	it('starts again from the first page on a new filter, and keeps the page size', () => {
		const params = new URLSearchParams('actor=G0007&page=4&size=50');
		const next = withFilters(params, { ...parseFilters(params), kev: true });
		expect(next.toString()).toBe('size=50&actor=G0007&kev=1');
	});

	it('opens one detail at a time', () => {
		const params = new URLSearchParams('actor=G0007&campaign=C0022');
		expect(withSelection(params, { report: 'abc' }).toString()).toBe('actor=G0007&report=abc');
		expect(withSelection(params, {}).toString()).toBe('actor=G0007');
	});
});
