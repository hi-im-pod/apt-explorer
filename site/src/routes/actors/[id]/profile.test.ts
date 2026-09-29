import { describe, it, expect } from 'vitest';
import type { Actor, Report } from '$lib/data';
import {
	actorSources,
	groupValues,
	pickReports,
	reportLinks,
	techniqueUrl,
	undatedCount
} from './profile';

function report(over: Partial<Report> & { id: string }): Report {
	return {
		title: `Report ${over.id}`,
		published: '2025-01-01',
		date_basis: 'publisher',
		organisation: null,
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

function actor(over: Partial<Actor>): Actor {
	return {
		id: 'G0001',
		name: 'Test',
		aliases: [{ value: 'Test', sources: ['misp'] }],
		origin: [],
		sponsor: [],
		motivation: [],
		claimed_targets: { countries: [], sectors: [] },
		malware: [],
		techniques_documented: [],
		techniques_reported: [],
		cves: [],
		timeline: [],
		reports: [],
		conflicts: [],
		evidence_count: 0,
		...over
	};
}

describe('reportLinks', () => {
	const url = 'https://vendor.example/post';
	const archive = 'https://archive.example/post.pdf';

	it('leads with the original link and offers the archive second', () => {
		expect(reportLinks({ url, url_ok: true, archive_url: archive })).toEqual({
			primary: { href: url, kind: 'original' },
			secondary: { href: archive, kind: 'archive' },
			originalFailed: false
		});
	});

	it('treats an unchecked link as working', () => {
		expect(reportLinks({ url, url_ok: null, archive_url: archive }).primary).toEqual({
			href: url,
			kind: 'original'
		});
	});

	it('leads with the archive when the original failed its last check', () => {
		expect(reportLinks({ url, url_ok: false, archive_url: archive })).toEqual({
			primary: { href: archive, kind: 'archive' },
			secondary: { href: url, kind: 'original' },
			originalFailed: true
		});
	});

	it('keeps a failed original when there is no archive, and says it failed', () => {
		expect(reportLinks({ url, url_ok: false, archive_url: null })).toEqual({
			primary: { href: url, kind: 'original' },
			secondary: null,
			originalFailed: true
		});
	});

	it('falls back to the archive alone, or to no link at all', () => {
		expect(reportLinks({ url: null, url_ok: null, archive_url: archive })).toEqual({
			primary: { href: archive, kind: 'archive' },
			secondary: null,
			originalFailed: false
		});
		expect(reportLinks({ url: null, url_ok: null, archive_url: null })).toEqual({
			primary: null,
			secondary: null,
			originalFailed: false
		});
	});
});

describe('groupValues', () => {
	it('shows a value once with every source that gives it, in first-seen order', () => {
		expect(
			groupValues([
				{ value: 'KP', source: 'misp' },
				{ value: 'Espionage', source: 'misp' },
				{ value: 'KP', source: 'malpedia' }
			])
		).toEqual([
			{ value: 'KP', sources: ['misp', 'malpedia'] },
			{ value: 'Espionage', sources: ['misp'] }
		]);
	});

	it('does not repeat a source that asserts the same value twice', () => {
		expect(
			groupValues([
				{ value: 'KP', source: 'misp' },
				{ value: 'KP', source: 'misp' }
			])
		).toEqual([{ value: 'KP', sources: ['misp'] }]);
	});
});

describe('actorSources', () => {
	it('lists every source behind any published field, in the About page order', () => {
		const a = actor({
			aliases: [{ value: 'X', sources: ['malpedia', 'misp'] }],
			origin: [{ value: 'CN', source: 'etda' }],
			malware: [{ name: 'Y', source: 'attack' }]
		});
		expect(actorSources(a)).toEqual(['attack', 'misp', 'etda', 'malpedia']);
	});

	it('puts a source the site has no label for last rather than dropping it', () => {
		const a = actor({ aliases: [{ value: 'X', sources: ['newsource', 'misp'] }] });
		expect(actorSources(a)).toEqual(['misp', 'newsource']);
	});
});

describe('undatedCount', () => {
	it('is the reports the timeline cannot place', () => {
		const a = actor({
			reports: ['a', 'b', 'c', 'd'],
			timeline: [
				{ quarter: '2024-Q1', count: 1 },
				{ quarter: '2025-Q3', count: 2 }
			]
		});
		expect(undatedCount(a)).toBe(1);
	});

	it('never goes below zero when the data disagrees with itself', () => {
		expect(undatedCount(actor({ reports: [], timeline: [{ quarter: '2024-Q1', count: 2 }] }))).toBe(0);
	});
});

describe('pickReports', () => {
	const shard = [report({ id: 'r1' }), report({ id: 'r2' }), report({ id: 'r3' })];
	const byId = new Map(shard.map((r) => [r.id, r]));

	it("keeps the actor's order and only the fields the page shows", () => {
		const { reports, missing } = pickReports(['r3', 'r1'], byId);
		expect(reports.map((r) => r.id)).toEqual(['r3', 'r1']);
		expect(Object.keys(reports[0]).sort()).toEqual(
			['archive_url', 'date_basis', 'id', 'organisation', 'published', 'sources', 'title', 'url', 'url_ok'].sort()
		);
		expect(missing).toEqual([]);
	});

	it('reports IDs that no shard holds instead of inventing rows', () => {
		const { reports, missing } = pickReports(['r2', 'gone'], byId);
		expect(reports.map((r) => r.id)).toEqual(['r2']);
		expect(missing).toEqual(['gone']);
	});
});

describe('techniqueUrl', () => {
	it('links techniques and sub-techniques to their ATT&CK pages', () => {
		expect(techniqueUrl('T1105')).toBe('https://attack.mitre.org/techniques/T1105/');
		expect(techniqueUrl('T1059.001')).toBe('https://attack.mitre.org/techniques/T1059/001/');
	});
});
