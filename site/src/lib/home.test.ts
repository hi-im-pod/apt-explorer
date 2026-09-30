import { describe, expect, it } from 'vitest';
import type { Actor } from './data/types';
import { aliasGrid, numberWord, publishShort } from './home';

function actor(aliases: [string, string[]][], name = 'Alpha'): Actor {
	return {
		id: 'G1',
		name,
		aliases: aliases.map(([value, sources]) => ({ value, sources })),
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
		evidence_count: 0
	};
}

describe('numberWord', () => {
	it('spells numbers up to 99', () => {
		expect(numberWord(0)).toBe('zero');
		expect(numberWord(4)).toBe('four');
		expect(numberWord(13)).toBe('thirteen');
		expect(numberWord(20)).toBe('twenty');
		expect(numberWord(46)).toBe('forty-six');
		expect(numberWord(99)).toBe('ninety-nine');
	});

	it('leaves larger numbers and odd input as digits', () => {
		expect(numberWord(100)).toBe('100');
		expect(numberWord(-1)).toBe('-1');
		expect(numberWord(2.5)).toBe('2.5');
	});
});

describe('publishShort', () => {
	it('names each policy in a few words', () => {
		expect(publishShort('full')).toBe('Full');
		expect(publishShort('derived-only')).toBe('Derived facts only');
		expect(publishShort('link-only')).toBe('Links only');
	});
});

describe('aliasGrid', () => {
	const order = ['attack', 'misp', 'etda', 'malpedia', 'orkl'];

	it('orders the columns as sources.json does and leaves out sources no name uses', () => {
		const g = aliasGrid(
			actor([
				['Alpha', ['malpedia', 'attack']],
				['Beta', ['etda']]
			]),
			order
		);
		expect(g.columns).toEqual(['attack', 'etda', 'malpedia']);
	});

	it('puts a source the order does not know after the known ones', () => {
		const g = aliasGrid(actor([['Alpha', ['zzz', 'attack']]]), order);
		expect(g.columns).toEqual(['attack', 'zzz']);
	});

	it('starts with the actor name and keeps every name when there are few', () => {
		const g = aliasGrid(
			actor([
				['Beta', ['attack']],
				['Alpha', ['attack', 'misp']],
				['Gamma', ['attack', 'misp', 'etda']]
			]),
			order
		);
		expect(g.rows.map((r) => r.name)).toEqual(['Alpha', 'Gamma', 'Beta']);
		expect(g.rows[0]).toEqual({ name: 'Alpha', sources: ['attack', 'misp'], primary: true });
		expect(g.rows.filter((r) => r.primary)).toHaveLength(1);
		expect(g.total).toBe(3);
	});

	it('samples evenly from the most to the least widely listed name', () => {
		const names: [string, string[]][] = [['Alpha', ['attack', 'misp', 'etda', 'malpedia']]];
		for (let i = 0; i < 40; i++) names.push([`N${i}`, order.slice(0, 1 + (i % 4))]);
		const g = aliasGrid(actor(names), order, 6);
		expect(g.rows).toHaveLength(6);
		expect(g.total).toBe(41);
		const counts = g.rows.slice(1).map((r) => r.sources.length);
		expect(counts).toEqual([...counts].sort((a, b) => b - a));
		expect(counts[0]).toBe(4);
		expect(counts[counts.length - 1]).toBe(1);
		expect(new Set(g.rows.map((r) => r.name)).size).toBe(6);
	});

	it('breaks ties by the order the data gives', () => {
		const g = aliasGrid(
			actor([
				['Alpha', ['attack']],
				['B', ['attack']],
				['C', ['attack']],
				['D', ['attack']]
			]),
			order,
			3
		);
		expect(g.rows.map((r) => r.name)).toEqual(['Alpha', 'B', 'D']);
	});

	it('still gives the actor a row when no claim carries its own name', () => {
		const g = aliasGrid(actor([['Beta', ['attack']]]), order);
		expect(g.rows[0]).toEqual({ name: 'Alpha', sources: [], primary: true });
		expect(g.rows).toHaveLength(2);
	});
});
