import { describe, expect, it } from 'vitest';
import { formatCount, formatDate } from './format';

describe('formatDate', () => {
	it('writes a date the same way in every locale and time zone', () => {
		// Prerender runs in Node and hydration in the visitor's browser. If the
		// two formatted dates differ, the text changes after load.
		expect(formatDate('2026-09-28T03:21:05Z')).toBe('28 September 2026');
		expect(formatDate('2026-01-01T00:30:00Z')).toBe('1 January 2026');
		expect(formatDate('2025-12-31')).toBe('31 December 2025');
	});

	it('says so when there is no date, rather than showing an empty cell', () => {
		expect(formatDate(null)).toBe('not reported');
	});

	it('rejects a string that is not a date', () => {
		expect(() => formatDate('soon')).toThrow(/soon/);
	});
});

describe('formatCount', () => {
	it('groups thousands with a comma', () => {
		expect(formatCount(29538)).toBe('29,538');
		expect(formatCount(118)).toBe('118');
		expect(formatCount(0)).toBe('0');
	});
});
