import { describe, it, expect } from 'vitest';
import type { Actor, Report } from '$lib/data';
import {
	actorSources,
	countWord,
	documentedOnly,
	groupValues,
	ledeFor,
	otherSources,
	linkNote,
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
		actors_from_title: [],
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
	const archive = 'https://archive.orkl.eu/aa.pdf';
	const VX = 'https://papers.vx-underground.org/papers/x.pdf';

	it('leads with the original link and offers the archived copy second, each named by its host', () => {
		expect(reportLinks({ url, url_ok: true, archive_url: archive })).toEqual({
			primary: { href: url, kind: 'original', label: 'Original publisher' },
			secondary: { href: archive, kind: 'copy', label: 'Archived copy on ORKL' },
			failed: null
		});
	});

	it('treats an unchecked link as working', () => {
		expect(reportLinks({ url, url_ok: null, archive_url: archive }).primary?.href).toBe(url);
		expect(reportLinks({ url, url_ok: null, archive_url: archive }).failed).toBeNull();
	});

	it('leads with the copy when the original failed its last check', () => {
		expect(reportLinks({ url, url_ok: false, archive_url: archive })).toEqual({
			primary: { href: archive, kind: 'copy', label: 'Archived copy on ORKL' },
			secondary: { href: url, kind: 'original', label: 'Original publisher' },
			failed: { href: url, kind: 'original', label: 'Original publisher' }
		});
	});

	it('keeps a failed original when there is no copy, and says it failed', () => {
		const out = reportLinks({ url, url_ok: false, archive_url: null });
		expect(out.primary?.href).toBe(url);
		expect(out.secondary).toBeNull();
		expect(out.failed?.href).toBe(url);
	});

	it('falls back to the copy alone, or to no link at all', () => {
		expect(reportLinks({ url: null, url_ok: null, archive_url: archive })).toEqual({
			primary: { href: archive, kind: 'copy', label: 'Archived copy on ORKL' },
			secondary: null,
			failed: null
		});
		expect(reportLinks({ url: null, url_ok: null, archive_url: null })).toEqual({
			primary: null,
			secondary: null,
			failed: null
		});
	});

	it('never calls a mirror in the url field the original', () => {
		const out = reportLinks({ url: VX, url_ok: null, archive_url: archive });
		expect(out.primary).toEqual({ href: VX, kind: 'copy', label: 'Mirror on VX-Underground' });
		expect(out.secondary?.kind).toBe('copy');
		expect([out.primary, out.secondary].some((l) => l?.kind === 'original')).toBe(false);
	});

	it('names a link the site cannot confirm as such', () => {
		const out = reportLinks({ url: 'https://t.co/abc', url_ok: null, archive_url: null });
		expect(out.primary).toEqual({ href: 'https://t.co/abc', kind: 'unconfirmed', label: 'Link, publisher not confirmed' });
	});

	it('drops an address that cannot be read as a web link', () => {
		expect(reportLinks({ url: 'not a url', url_ok: null, archive_url: archive }).primary?.href).toBe(archive);
	});
});

describe('linkNote', () => {
	const copy = { href: 'x', kind: 'copy', label: 'Mirror on VX-Underground' } as const;
	const original = { href: 'x', kind: 'original', label: 'Original publisher' } as const;
	const unconfirmed = { href: 'x', kind: 'unconfirmed', label: 'Link, publisher not confirmed' } as const;

	it('says what the title opens when it is not the publisher', () => {
		expect(linkNote({ primary: copy, secondary: null, failed: null })).toBe(
			'The title opens Mirror on VX-Underground, not the publisher’s page.'
		);
		expect(linkNote({ primary: unconfirmed, secondary: null, failed: null })).toBe(
			'The title opens a link whose publisher is not confirmed.'
		);
	});

	it('says which link failed its last check, using its own name', () => {
		expect(linkNote({ primary: copy, secondary: original, failed: original })).toBe(
			'The original link failed its last check.'
		);
		expect(linkNote({ primary: original, secondary: null, failed: copy })).toBe(
			'The link to Mirror on VX-Underground failed its last check.'
		);
	});

	it('says nothing when the title opens the original and nothing failed', () => {
		expect(linkNote({ primary: original, secondary: copy, failed: null })).toBeNull();
		expect(linkNote({ primary: null, secondary: null, failed: null })).toBeNull();
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

describe('countWord', () => {
	it('spells out numbers under ten and uses numerals from ten', () => {
		expect(countWord(1)).toBe('one');
		expect(countWord(3)).toBe('three');
		expect(countWord(9)).toBe('nine');
		expect(countWord(10)).toBe('10');
		expect(countWord(1234)).toBe('1,234');
	});
});

describe('ledeFor', () => {
	const aliases = (...names: string[]) => names.map((value) => ({ value, sources: ['misp' as const] }));

	it('names the first five other names, counts the rest and says how many sources agree on an origin', () => {
		const a = actor({
			name: 'APT28',
			aliases: aliases('APT28', 'Fancy Bear', 'Sofacy', 'Sednit', 'Pawn Storm', 'Forest Blizzard', 'STRONTIUM', 'BlueDelta'),
			origin: [
				{ value: 'RU', source: 'misp' },
				{ value: 'RU', source: 'etda' },
				{ value: 'RU', source: 'malpedia' }
			]
		});
		expect(ledeFor(a)).toBe(
			'Also reported as Fancy Bear, Sofacy, Sednit, Pawn Storm, Forest Blizzard and 2 other names. Linked to Russia by three sources.'
		);
	});

	it('lists a short set of names in full, with "and" before the last', () => {
		expect(ledeFor(actor({ name: 'X', aliases: aliases('X', 'A', 'B') }))).toBe('Also reported as A and B.');
		expect(ledeFor(actor({ name: 'X', aliases: aliases('X', 'A', 'B', 'C') }))).toBe('Also reported as A, B and C.');
		expect(ledeFor(actor({ name: 'X', aliases: aliases('X', 'A') }))).toBe('Also reported as A.');
	});

	it('uses the singular for one source and says when sources disagree', () => {
		expect(ledeFor(actor({ origin: [{ value: 'KP', source: 'misp' }] }))).toBe('Linked to North Korea by one source.');
		expect(
			ledeFor(
				actor({
					origin: [
						{ value: 'CN', source: 'misp' },
						{ value: 'RU', source: 'etda' }
					]
				})
			)
		).toBe('Sources disagree on the origin.');
	});

	it('is null for an actor with no other names and no origin', () => {
		expect(ledeFor(actor({ name: 'Test' }))).toBeNull();
	});
});

describe('documentedOnly', () => {
	it('keeps the ATT&CK techniques that no recent report names, in order', () => {
		const a = actor({
			techniques_documented: ['T1', 'T2', 'T3', 'T4'],
			techniques_reported: [
				{ id: 'T3', count: 5 },
				{ id: 'T9', count: 2 }
			]
		});
		expect(documentedOnly(a)).toEqual(['T1', 'T2', 'T4']);
	});
});

describe('otherSources', () => {
	it('leaves out the four sources that have a box and keeps the rest', () => {
		expect(otherSources(['attack', 'paper', 'malpedia', 'kev'])).toEqual(['paper', 'kev']);
	});
});

describe('techniqueUrl', () => {
	it('links techniques and sub-techniques to their ATT&CK pages', () => {
		expect(techniqueUrl('T1105')).toBe('https://attack.mitre.org/techniques/T1105/');
		expect(techniqueUrl('T1059.001')).toBe('https://attack.mitre.org/techniques/T1059/001/');
	});
});
