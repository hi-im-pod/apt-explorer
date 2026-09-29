import { describe, expect, it } from 'vitest';
import type { Trends } from '$lib/data/types';
import {
	kevMonthly,
	monthRange,
	newActorMonths,
	quarterOf,
	quarterRange,
	reportedVsDocumented,
	reportingActivity
} from './series';

// A small trends.json, so each case states what it depends on.
function trends(over: Partial<Trends>): Trends {
	return {
		window_start: '2024-01-01',
		generated_at: '2025-02-10T03:00:00Z',
		reporting_activity: [],
		new_actors: [],
		kev_monthly: [],
		kev_actor_links: [],
		reported_vs_documented: [],
		source_health: [],
		notes: {
			reporting_activity: '',
			new_actors: '',
			kev_monthly: '',
			kev_actor_links: '',
			reported_vs_documented: '',
			source_health: ''
		},
		...over
	};
}

describe('calendar helpers', () => {
	it('names the quarter of a date or timestamp', () => {
		expect(quarterOf('2024-01-01')).toBe('2024-Q1');
		expect(quarterOf('2024-12-31')).toBe('2024-Q4');
		expect(quarterOf('2025-05-10T03:00:00Z')).toBe('2025-Q2');
	});

	it('lists quarters and months inclusively, across a year end', () => {
		expect(quarterRange('2024-Q3', '2025-Q2')).toEqual(['2024-Q3', '2024-Q4', '2025-Q1', '2025-Q2']);
		expect(monthRange('2024-11', '2025-02')).toEqual(['2024-11', '2024-12', '2025-01', '2025-02']);
		expect(quarterRange('2025-Q1', '2024-Q4')).toEqual([]);
	});
});

describe('reportingActivity', () => {
	const t = trends({
		reporting_activity: [
			// Before the window: must not start the axis early or count towards a rank.
			{ actor: 'G0001', quarter: '2023-Q4', count: 9, prev_year_count: 0 },
			{ actor: 'G0001', quarter: '2024-Q2', count: 1, prev_year_count: 2 },
			{ actor: 'G0002', quarter: '2024-Q1', count: 3, prev_year_count: 0 },
			{ actor: 'G0002', quarter: '2024-Q4', count: 2, prev_year_count: 1 },
			{ actor: 'G0003', quarter: '2025-Q1', count: 2, prev_year_count: 0 }
		]
	});

	it('starts at window_start and runs to the quarter of the build, with no gaps', () => {
		const a = reportingActivity(t, 6);
		expect(a.quarters).toEqual(['2024-Q1', '2024-Q2', '2024-Q3', '2024-Q4', '2025-Q1']);
		expect(a.points.every((p) => p.quarter >= '2024-Q1')).toBe(true);
	});

	it('ranks actors by reports inside the window only', () => {
		// G0001 has 9 reports in 2023, which do not count.
		expect(reportingActivity(t, 6).actors).toEqual(['G0002', 'G0003', 'G0001']);
		expect(reportingActivity(t, 2).actors).toEqual(['G0002', 'G0003']);
	});

	it('fills quarters with no row as zero, and keeps the year-earlier count', () => {
		const g2 = reportingActivity(t, 6).points.filter((p) => p.actor === 'G0002');
		expect(g2.map((p) => [p.quarter, p.count, p.prev])).toEqual([
			['2024-Q1', 3, 0],
			['2024-Q2', 0, 0],
			['2024-Q3', 0, 0],
			['2024-Q4', 2, 1],
			['2025-Q1', 0, 0]
		]);
		expect(g2[0].start.toISOString()).toBe('2024-01-01T00:00:00.000Z');
		expect(g2[0].end.toISOString()).toBe('2024-04-01T00:00:00.000Z');
	});
});

describe('kevMonthly', () => {
	const t = trends({
		kev_monthly: [
			{ month: '2023-12', added: 30, ransomware: 3 },
			{ month: '2024-01', added: 10, ransomware: 4 },
			{ month: '2024-03', added: 5, ransomware: 5 }
		]
	});

	it('runs from the window start to the build month, zero-filled, never earlier', () => {
		const k = kevMonthly(t);
		expect(k[0].month).toBe('2024-01');
		expect(k.at(-1)?.month).toBe('2025-02');
		expect(k).toHaveLength(14);
		expect(k.find((p) => p.month === '2024-02')).toMatchObject({ added: 0, ransomware: 0, other: 0 });
	});

	it('splits each month into ransomware and other additions', () => {
		const k = kevMonthly(t);
		expect(k[0]).toMatchObject({ added: 10, ransomware: 4, other: 6 });
		expect(k[2]).toMatchObject({ added: 5, ransomware: 5, other: 0 });
	});
});

describe('reportedVsDocumented', () => {
	const row = (actor: string, reported: number, overlap: number) => ({
		actor,
		reported_only: Array.from({ length: reported }, (_, i) => `T${1000 + i}`),
		documented_only_count: 7,
		overlap
	});

	it('puts the actors with the most reported-only techniques first and drops empty rows', () => {
		const t = trends({
			reported_vs_documented: [row('a', 0, 4), row('b', 2, 1), row('c', 2, 3), row('d', 0, 0)]
		});
		const bars = reportedVsDocumented(t, 15);
		expect(bars.map((b) => b.actor)).toEqual(['c', 'b', 'a']);
		expect(bars[0]).toMatchObject({ reportedOnly: 2, overlap: 3, ids: ['T1000', 'T1001'] });
	});

	it('keeps at most the requested number of actors', () => {
		const t = trends({
			reported_vs_documented: Array.from({ length: 20 }, (_, i) => row(`x${i}`, 1, i))
		});
		expect(reportedVsDocumented(t, 15)).toHaveLength(15);
	});
});

describe('newActorMonths', () => {
	it('counts new actors per month over the twelve months up to the build', () => {
		const t = trends({
			generated_at: '2026-09-28T03:17:42Z',
			new_actors: [
				{ actor: 'a', first_seen: '2026-02-11', basis: 'report' },
				{ actor: 'b', first_seen: '2026-02-20', basis: 'misp' },
				{ actor: 'c', first_seen: '2025-10-01', basis: 'misp' }
			]
		});
		const m = newActorMonths(t);
		expect(m.map((p) => p.month)).toEqual(monthRange('2025-10', '2026-09'));
		expect(m.find((p) => p.month === '2026-02')?.count).toBe(2);
		expect(m.find((p) => p.month === '2025-10')?.count).toBe(1);
	});

	it('never starts before the window', () => {
		const t = trends({ generated_at: '2024-05-02T00:00:00Z' });
		expect(newActorMonths(t)[0].month).toBe('2024-01');
	});
});
