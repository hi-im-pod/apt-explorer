import { describe, expect, it } from 'vitest';
import {
	DEFAULT_SIZE,
	clampPage,
	pageCount,
	pageOfIndex,
	pageWindow,
	parsePaging,
	rangeLabel,
	withPaging
} from './paging';

describe('parsePaging', () => {
	it('defaults to page 1 of 25 rows', () => {
		expect(parsePaging(new URLSearchParams(''))).toEqual({ page: 1, size: DEFAULT_SIZE });
		expect(DEFAULT_SIZE).toBe(25);
	});
	it('reads a page and an allowed size', () => {
		expect(parsePaging(new URLSearchParams('page=7&size=50'))).toEqual({ page: 7, size: 50 });
	});
	it('falls back on anything malformed', () => {
		for (const q of ['page=0', 'page=-3', 'page=abc', 'page=2.5', 'page=', 'size=30', 'size=0', 'size=x']) {
			const p = parsePaging(new URLSearchParams(q));
			expect(p.page).toBeGreaterThanOrEqual(1);
			expect([25, 50, 100]).toContain(p.size);
		}
		expect(parsePaging(new URLSearchParams('page=abc')).page).toBe(1);
		expect(parsePaging(new URLSearchParams('size=30')).size).toBe(25);
	});
});

describe('pageCount and clampPage', () => {
	it('counts pages, with at least one', () => {
		expect(pageCount(0, 25)).toBe(1);
		expect(pageCount(25, 25)).toBe(1);
		expect(pageCount(26, 25)).toBe(2);
		expect(pageCount(1000, 100)).toBe(10);
	});
	it('clamps an out-of-range page', () => {
		expect(clampPage(99, 60, 25)).toBe(3);
		expect(clampPage(1, 0, 25)).toBe(1);
		expect(clampPage(2, 60, 25)).toBe(2);
	});
});

describe('pageWindow', () => {
	it('lists every page when there are few', () => {
		expect(pageWindow(1, 1)).toEqual([1]);
		expect(pageWindow(3, 5)).toEqual([1, 2, 3, 4, 5]);
		expect(pageWindow(3, 7)).toEqual([1, 2, 3, 4, 'gap', 7]);
	});
	it('shows first, last, and the current page with its neighbours', () => {
		expect(pageWindow(6, 20)).toEqual([1, 'gap', 5, 6, 7, 'gap', 20]);
	});
	it('does not turn a single skipped page into a gap', () => {
		expect(pageWindow(4, 20)).toEqual([1, 2, 3, 4, 5, 'gap', 20]);
		expect(pageWindow(17, 20)).toEqual([1, 'gap', 16, 17, 18, 19, 20]);
	});
	it('handles the ends', () => {
		expect(pageWindow(1, 20)).toEqual([1, 2, 'gap', 20]);
		expect(pageWindow(20, 20)).toEqual([1, 'gap', 19, 20]);
	});
});

describe('rangeLabel', () => {
	it('names the rows on the page and the matching total', () => {
		expect(rangeLabel(2, 25, 3412)).toBe('Rows 26 to 50 of 3,412 matching');
	});
	it('ends the last page at the total', () => {
		expect(rangeLabel(3, 25, 60)).toBe('Rows 51 to 60 of 60 matching');
	});
	it('says so when nothing matches', () => {
		expect(rangeLabel(1, 25, 0)).toBe('No rows match');
	});
});

describe('withPaging', () => {
	it('keeps other keys and omits defaults', () => {
		const base = new URLSearchParams('q=apt&report=x');
		expect(withPaging(base, { page: 1, size: 25 }).toString()).toBe('q=apt&report=x');
		expect(withPaging(base, { page: 3, size: 50 }).toString()).toBe('q=apt&report=x&page=3&size=50');
	});
	it('replaces earlier values', () => {
		expect(withPaging(new URLSearchParams('page=9&size=100'), { page: 2, size: 25 }).toString()).toBe('page=2');
	});
});

describe('pageOfIndex', () => {
	it('gives the page a row index falls on', () => {
		expect(pageOfIndex(0, 25)).toBe(1);
		expect(pageOfIndex(24, 25)).toBe(1);
		expect(pageOfIndex(25, 25)).toBe(2);
	});
});
