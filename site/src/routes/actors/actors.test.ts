import { describe, it, expect } from 'vitest';
import type { ActorsIndexEntry } from '$lib/data';
import { countryName, matchActor, searchKey, sortActors } from './actors';

function entry(over: Partial<ActorsIndexEntry> & { id: string; name: string }): ActorsIndexEntry {
	return {
		aliases: [over.name],
		origin: [],
		origin_conflict: false,
		report_count: 0,
		last_reported: null,
		sources: ['attack'],
		...over
	};
}

const apt28 = entry({
	id: 'G0007',
	name: 'APT28',
	aliases: ['APT28', 'Fancy Bear', 'Sofacy', 'Sednit'],
	report_count: 10,
	last_reported: '2026-09-09'
});
const apt2 = entry({ id: 'apt2', name: 'APT2', report_count: 0 });
const lazarus = entry({
	id: 'G0032',
	name: 'Lazarus Group',
	aliases: ['Lazarus Group', 'HIDDEN COBRA', 'Lazarus-Group-Umbrella-Cluster'],
	report_count: 14,
	last_reported: '2026-09-22'
});
const heron = entry({ id: 'glass-heron', name: 'Glass Heron', report_count: 2, last_reported: '2026-09-22' });

describe('searchKey', () => {
	it('ignores case, spacing, punctuation and full-width forms', () => {
		const keys = new Set(['Lazarus Group', 'LAZARUS-group', 'lazarus  group', 'Ｌａｚａｒｕｓ Group'].map(searchKey));
		expect(keys).toEqual(new Set(['lazarusgroup']));
	});

	it('keeps digits, so APT 28 and APT28 agree', () => {
		expect(searchKey('APT 28')).toBe(searchKey('APT28'));
	});
});

describe('matchActor', () => {
	it('matches everything on an empty or blank query', () => {
		expect(matchActor(apt28, '')).toEqual({ via: null });
		expect(matchActor(apt28, '  - ')).toEqual({ via: null });
	});

	it('matches the name and the ID without naming an alias', () => {
		expect(matchActor(apt28, 'apt 28')).toEqual({ via: null });
		expect(matchActor(apt28, 'g0007')).toEqual({ via: null });
	});

	it('names the alias that matched when the name did not', () => {
		expect(matchActor(apt28, 'fancy-bear')).toEqual({ via: 'Fancy Bear' });
		expect(matchActor(lazarus, 'umbrella')).toEqual({ via: 'Lazarus-Group-Umbrella-Cluster' });
	});

	it('returns null when nothing matches', () => {
		expect(matchActor(apt2, 'sofacy')).toBeNull();
	});
});

describe('sortActors', () => {
	const all = [apt2, heron, apt28, lazarus];

	it('puts the most recently reported first, ties by name, never-reported last', () => {
		expect(sortActors(all, 'recent').map((a) => a.id)).toEqual(['glass-heron', 'G0032', 'G0007', 'apt2']);
	});

	it('sorts by report count, most first', () => {
		expect(sortActors(all, 'reports').map((a) => a.id)).toEqual(['G0032', 'G0007', 'glass-heron', 'apt2']);
	});

	it('sorts by name without regard to case', () => {
		const lower = entry({ id: 'x', name: 'apt1' });
		expect(sortActors([lazarus, apt28, lower], 'name').map((a) => a.name)).toEqual([
			'apt1',
			'APT28',
			'Lazarus Group'
		]);
	});

	it('does not reorder the array it was given', () => {
		const copy = [...all];
		sortActors(all, 'name');
		expect(all).toEqual(copy);
	});
});

describe('countryName', () => {
	it('names the ISO codes the sources use for origin', () => {
		expect(countryName('KP')).toBe('North Korea');
		expect(countryName('GB')).toBe('United Kingdom');
	});

	it('returns anything it does not know unchanged', () => {
		expect(countryName('ZZ')).toBe('ZZ');
		expect(countryName('Atlantis')).toBe('Atlantis');
	});
});
