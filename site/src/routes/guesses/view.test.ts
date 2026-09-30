import { describe, it, expect } from 'vitest';
import type { Guess } from '$lib/data/types';
import {
	bandText,
	confidenceText,
	countBy,
	filterGuesses,
	gainText,
	kindText,
	labelText,
	percentText,
	weightText,
	directionText
} from './view';

function guess(over: Partial<Guess>): Guess {
	return {
		name: 'Name',
		count: 1,
		label: 'actor',
		confidence: 0.9,
		band: 'high',
		matched_actor_id: null,
		matched_actor_name: null,
		evidence: [],
		status: 'pending confirmation',
		...over
	};
}

const rows: Guess[] = [
	guess({ name: 'Sofacy Gang', label: 'actor', band: 'high', matched_actor_id: 'G0007', matched_actor_name: 'APT28' }),
	guess({ name: 'Blorp Loader', label: 'malware', band: 'medium', confidence: 0.75 }),
	guess({ name: 'Operation Zeta', label: 'not-an-entity', band: 'unvalidated', confidence: null }),
	guess({ name: 'Kittenfoo', label: 'actor', band: 'confirmed', confidence: null, status: 'confirmed' })
];

describe('labels and bands', () => {
	it('spells each label for a reader', () => {
		expect(labelText('not-an-entity')).toBe('Not an entity');
		expect(labelText('malware')).toBe('Malware');
	});

	it('spells each band, with the confidence only when there is one', () => {
		expect(bandText('unvalidated')).toBe('Unvalidated');
		expect(confidenceText(rows[0])).toBe('High, 90%');
		expect(confidenceText(rows[2])).toBe('Unvalidated');
		expect(confidenceText(rows[3])).toBe('Confirmed');
	});

	it('rounds a confidence to a whole percent and never shows 100 for less than certain', () => {
		expect(confidenceText(guess({ confidence: 0.996, band: 'high' }))).toBe('High, 99%');
		expect(confidenceText(guess({ confidence: 0.5, band: 'low' }))).toBe('Low, 50%');
	});
});

describe('filterGuesses', () => {
	it('returns everything when no filter is set', () => {
		expect(filterGuesses(rows, { label: 'all', band: 'all', query: '' })).toHaveLength(4);
	});

	it('filters by label, band and text together', () => {
		expect(filterGuesses(rows, { label: 'actor', band: 'all', query: '' }).map((g) => g.name)).toEqual([
			'Sofacy Gang',
			'Kittenfoo'
		]);
		expect(filterGuesses(rows, { label: 'actor', band: 'high', query: '' }).map((g) => g.name)).toEqual([
			'Sofacy Gang'
		]);
		expect(filterGuesses(rows, { label: 'all', band: 'all', query: '  loader ' }).map((g) => g.name)).toEqual([
			'Blorp Loader'
		]);
	});

	it('finds a guess by the actor it is matched to', () => {
		expect(filterGuesses(rows, { label: 'all', band: 'all', query: 'apt28' }).map((g) => g.name)).toEqual([
			'Sofacy Gang'
		]);
	});

	it('returns nothing, not everything, when nothing matches', () => {
		expect(filterGuesses(rows, { label: 'all', band: 'all', query: 'zzz' })).toEqual([]);
	});
});

describe('countBy', () => {
	it('counts each label and band, including the ones that are absent', () => {
		expect(countBy(rows, (g) => g.label, ['actor', 'malware', 'tool', 'not-an-entity'])).toEqual({
			actor: 2,
			malware: 1,
			tool: 0,
			'not-an-entity': 1
		});
	});
});

describe('weightText', () => {
	it('signs the weight and says which way it points', () => {
		expect(weightText(1.234)).toBe('+1.2 supports the guess');
		expect(weightText(-0.5)).toBe('-0.5 argues against it');
		expect(weightText(null)).toBe('context only');
		expect(weightText(0)).toBe('context only');
	});
});

describe('directionText', () => {
	it('names the label a kept signal pushes toward and how hard', () => {
		expect(directionText(0.939)).toBe('pushes toward malware, strength 0.9');
		expect(directionText(-0.829)).toBe('pushes toward actor, strength 0.8');
	});

	it('says nothing is pushed for a missing or zero weight', () => {
		expect(directionText(null)).toBeNull();
		expect(directionText(0)).toBeNull();
	});
});

describe('percentText', () => {
	it('rounds to a whole percent and says n/a for a missing figure', () => {
		expect(percentText(0.75)).toBe('75%');
		expect(percentText(0.6884)).toBe('69%');
		expect(percentText(0)).toBe('0%');
		expect(percentText(null)).toBe('n/a');
	});
});

describe('kindText', () => {
	it('describes each kind of match in words', () => {
		expect(kindText('variant')).toMatch(/suffix/i);
		expect(kindText('contains')).toMatch(/contains/i);
		expect(kindText('fuzzy')).toMatch(/close/i);
	});
});

describe('gainText', () => {
	it('says how far the method is above the plain answer, in points', () => {
		expect(gainText(0.75, 0.688)).toBe('6 points above');
		expect(gainText(0.7, 0.7)).toBe('level with');
		expect(gainText(0.6, 0.7)).toBe('10 points below');
		expect(gainText(0.752, 0.75)).toBe('level with');
	});

	it('returns null when either figure is missing', () => {
		expect(gainText(null, 0.5)).toBeNull();
		expect(gainText(0.5, null)).toBeNull();
	});
});
