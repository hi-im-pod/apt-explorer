import { describe, expect, it } from 'vitest';
import type { ActorsIndex, Campaign, Report, Vuln } from '$lib/data/types';
import {
	applyFilters,
	buildIndex,
	parseFilters,
	toRows,
	withFilters,
	withSelection,
	type ExploreRow
} from './search';

// Small hand-made inputs, so each case states exactly what it depends on.
function report(over: Partial<Report> & Pick<Report, 'id'>): Report {
	return {
		title: `Report ${over.id}`,
		published: '2024-05-01',
		date_basis: 'publisher',
		organisation: 'Harbor CERT',
		url: `https://example.org/${over.id}`,
		url_ok: true,
		archive_url: null,
		actors: [],
		actor_names_unresolved: [],
		cves: [],
		techniques: [],
		sources: ['dfir'],
		...over
	};
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

function vuln(cve: string, kev: boolean): Vuln {
	return {
		cve,
		kev_date_added: kev ? '2023-03-14' : null,
		ransomware: kev ? false : null,
		vendor: null,
		product: null,
		actors: [],
		report_count: 1
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

const reports: Report[] = [
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
	report({ id: 'r-undated', published: null, date_basis: 'unknown', actors: ['G0007'] })
];

const campaigns: Campaign[] = [
	campaign({ id: 'C0022', name: 'Operation Dream Job', actors: ['G0032'], techniques: ['T1566.002'] }),
	campaign({ id: 'C9999', name: 'Still going', first_seen: '2023-06-01', last_seen: null, actors: ['G0007'] })
];

const vulns: Vuln[] = [
	vuln('CVE-2023-23397', true),
	vuln('CVE-2021-44228', true),
	vuln('CVE-2026-100123', false)
];

const rows = toRows(reports, campaigns, vulns, actors);
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

	it('marks a row KEV only when one of its CVEs has a KEV date', () => {
		const kev = Object.fromEntries(rows.map((r) => [r.id, r.kev]));
		expect(kev['r-2024-apt28']).toBe(true);
		expect(kev['r-2024-other-cve']).toBe(false);
		expect(kev['C0022']).toBe(false);
	});

	it('drops the publisher and unresolved names of an ORKL row, which is link-only', () => {
		// ORKL's terms are pending, so the site shows only a report's title,
		// date and links. Clearing the fields here means no table cell, filter
		// or search result can reveal them either.
		const [orkl] = toRows(
			[
				report({
					id: 'orkl-1',
					sources: ['orkl'],
					organisation: 'Northwind Threat Research',
					actor_names_unresolved: ['Some Tag']
				})
			],
			[],
			[],
			actors
		);
		expect(orkl.linkOnly).toBe(true);
		expect(orkl.organisation).toBeNull();
		expect(orkl.unresolved).toEqual([]);
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
			'C9999',
			'r-undated'
		]);
	});

	it('matches a technique with its sub-techniques, and a CVE by prefix, in any case', () => {
		expect(ids(applyFilters(rows, { tech: 't1566' }))).toEqual(['r-2024-lazarus', 'C0022']);
		expect(ids(applyFilters(rows, { cve: 'cve-2023' }))).toEqual(['r-2024-apt28']);
	});

	it('filters by source and by publisher', () => {
		expect(ids(applyFilters(rows, { source: 'attack' }))).toEqual(['C9999', 'C0022']);
		expect(ids(applyFilters(rows, { org: 'Blue Meridian Labs' }))).toEqual(['r-2024-lazarus']);
	});

	it('searches titles, publishers and actor aliases through the index', () => {
		const index = buildIndex(rows);
		expect(ids(applyFilters(rows, { q: 'fancy bear' }, index))).toEqual(['r-2024-apt28', 'r-2023', 'C9999']);
		expect(ids(applyFilters(rows, { q: 'log4shell' }, index))).toEqual(['r-2024-lazarus']);
		expect(ids(applyFilters(rows, { q: 'dream' }, index))).toEqual(['C0022']);
	});

	it('falls back to a title match when no index is given', () => {
		expect(ids(applyFilters(rows, { q: 'LOG4SHELL' }))).toEqual(['r-2024-lazarus']);
	});

	it('keeps a report and a campaign apart when they share an ID', () => {
		const clash = toRows(
			[report({ id: 'dfir:x', title: 'Alpha' })],
			[campaign({ id: 'dfir:x', name: 'Beta', source: 'dfir', first_seen: '2024-01-01' })],
			[],
			[]
		);
		const index = buildIndex(clash);
		expect(applyFilters(clash, { q: 'beta' }, index).map((r) => r.kind)).toEqual(['campaign']);
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

	it('opens one detail at a time', () => {
		const params = new URLSearchParams('actor=G0007&campaign=C0022');
		expect(withSelection(params, { report: 'abc' }).toString()).toBe('actor=G0007&report=abc');
		expect(withSelection(params, {}).toString()).toBe('actor=G0007');
	});
});
