import { describe, it, expect } from 'vitest';
import { render } from 'svelte/server';
import Timeline, { fillQuarters } from './Timeline.svelte';

describe('fillQuarters', () => {
	it('fills the quarters between the first and the last with zero', () => {
		expect(
			fillQuarters([
				{ quarter: '2023-Q4', count: 1 },
				{ quarter: '2024-Q3', count: 2 }
			])
		).toEqual([
			{ quarter: '2023-Q4', count: 1 },
			{ quarter: '2024-Q1', count: 0 },
			{ quarter: '2024-Q2', count: 0 },
			{ quarter: '2024-Q3', count: 2 }
		]);
	});

	it('sorts its input and returns nothing for nothing', () => {
		expect(
			fillQuarters([
				{ quarter: '2025-Q1', count: 3 },
				{ quarter: '2024-Q4', count: 1 }
			]).map((p) => p.quarter)
		).toEqual(['2024-Q4', '2025-Q1']);
		expect(fillQuarters([])).toEqual([]);
	});

	it('handles a single quarter', () => {
		expect(fillQuarters([{ quarter: '2026-Q2', count: 4 }])).toEqual([{ quarter: '2026-Q2', count: 4 }]);
	});
});

/** Every bar's inline height, in document order. */
const barHeights = (html: string) => [...html.matchAll(/class="bar[^"]*" style="height: ([^"]+)"/g)].map((m) => m[1]);
const columns = (html: string) => html.match(/<li\b/g)?.length ?? 0;

describe('Timeline', () => {
	it('draws one column per quarter across a decade, with every non-empty bar visible', () => {
		// A busy actor: 2014-Q1 to 2026-Q3 is 51 quarters, one of them
		// with 300 reports and one with a single report.
		const points = [
			{ quarter: '2014-Q1', count: 1 },
			{ quarter: '2020-Q2', count: 300 },
			{ quarter: '2026-Q3', count: 12 }
		];
		const { body } = render(Timeline, { props: { points, undated: 0 } });
		expect(columns(body)).toBe(51);
		const heights = barHeights(body);
		expect(heights).toHaveLength(3);
		// The smallest bar keeps a floor, so one report next to three
		// hundred is still something a reader can see.
		expect(heights[0]).toMatch(/^max\(2px, 0\.3\d*%\)$/);
		expect(heights[1]).toBe('max(2px, 100%)');
		expect(body).toContain('2014 Q1');
		expect(body).toContain('2026 Q3');
		expect(body).toMatch(/300/);
	});

	it('says how many undated reports it leaves out', () => {
		const { body } = render(Timeline, {
			props: { points: [{ quarter: '2024-Q1', count: 2 }], undated: 3 }
		});
		expect(body).toMatch(/3 undated reports/);
		const one = render(Timeline, { props: { points: [{ quarter: '2024-Q1', count: 2 }], undated: 1 } });
		expect(one.body).toMatch(/1 undated report\b/);
	});

	it('gives each quarter a text label for screen readers', () => {
		const { body } = render(Timeline, {
			props: {
				points: [
					{ quarter: '2024-Q1', count: 2 },
					{ quarter: '2024-Q3', count: 1 }
				],
				undated: 0
			}
		});
		expect(body).toContain('2024 Q1: 2 reports');
		expect(body).toContain('2024 Q2: no reports');
		expect(body).toContain('2024 Q3: 1 report');
	});
});
