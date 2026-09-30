import { describe, expect, it } from 'vitest';
import { pickTicks } from './ticks';

const months = (from: string, n: number): Date[] => {
	const [y, m] = from.split('-').map(Number);
	return Array.from({ length: n }, (_, i) => new Date(Date.UTC(y, m - 1 + i, 1)));
};

describe('pickTicks for months', () => {
	// 33 months from January 2024, like the KEV chart.
	const starts = months('2024-01', 33);

	it('labels every month when the chart is wide enough, with the year where it changes', () => {
		const t = pickTicks(starts, 'month', { plotWidth: 4000, leftRoom: 40, rightRoom: 8 });
		expect(t.ticks).toHaveLength(33);
		expect(t.format(starts[0])).toBe('Jan 2024');
		expect(t.format(starts[1])).toBe('Feb');
		expect(t.format(starts[12])).toBe('Jan 2025');
	});

	it('thins the ticks on a narrow chart, and always keeps the first', () => {
		const wide = pickTicks(starts, 'month', { plotWidth: 1200, leftRoom: 40, rightRoom: 8 });
		const narrow = pickTicks(starts, 'month', { plotWidth: 300, leftRoom: 40, rightRoom: 8 });
		expect(narrow.ticks.length).toBeLessThan(wide.ticks.length);
		expect(narrow.ticks[0]).toEqual(starts[0]);
		expect(narrow.format(narrow.ticks[0])).toBe('Jan 2024');
	});

	it('never places two labels closer than their widths allow', () => {
		for (const plotWidth of [200, 300, 500, 800, 1240]) {
			const t = pickTicks(starts, 'month', { plotWidth, leftRoom: 40, rightRoom: 8 });
			const pitch = plotWidth / starts.length;
			for (let i = 1; i < t.ticks.length; i++) {
				const a = starts.findIndex((s) => s.getTime() === t.ticks[i - 1].getTime());
				const b = starts.findIndex((s) => s.getTime() === t.ticks[i].getTime());
				const need = (t.format(t.ticks[i - 1]).length + t.format(t.ticks[i]).length) * 3.8;
				expect((b - a) * pitch, `${plotWidth}px, tick ${i}`).toBeGreaterThanOrEqual(need);
			}
		}
	});

	it('gives a year to the first tick after the year changes, even when January is skipped', () => {
		const t = pickTicks(months('2024-02', 20), 'month', { plotWidth: 300, leftRoom: 40, rightRoom: 8 });
		const labels = t.ticks.map((d) => t.format(d));
		expect(labels[0]).toMatch(/2024$/);
		const later = t.ticks.filter((d) => d.getUTCFullYear() === 2025).map((d) => t.format(d));
		expect(later[0]).toMatch(/2025$/);
	});

	it('drops a last tick whose label would run past the right edge', () => {
		const t = pickTicks(months('2024-01', 12), 'month', { plotWidth: 130, leftRoom: 40, rightRoom: 0 });
		const last = t.ticks[t.ticks.length - 1];
		const idx = months('2024-01', 12).findIndex((s) => s.getTime() === last.getTime());
		expect((idx * 130) / 12 + (t.format(last).length * 7.6) / 2).toBeLessThanOrEqual(130);
	});

	it('returns no ticks for no periods', () => {
		expect(pickTicks([], 'month', { plotWidth: 300, leftRoom: 40, rightRoom: 8 }).ticks).toEqual([]);
	});
});

describe('pickTicks for quarters', () => {
	const starts = [0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30].map((m) => new Date(Date.UTC(2024, m, 1)));

	it('labels each quarter as Q1 to Q4, with the year on the first and after a year change', () => {
		const t = pickTicks(starts, 'quarter', { plotWidth: 1200, leftRoom: 32, rightRoom: 8 });
		expect(t.ticks).toHaveLength(11);
		expect(t.format(starts[0])).toBe('Q1 2024');
		expect(t.format(starts[1])).toBe('Q2');
		expect(t.format(starts[4])).toBe('Q1 2025');
	});

	it('shows every second quarter at phone width, starting at the first', () => {
		const t = pickTicks(starts, 'quarter', { plotWidth: 300, leftRoom: 32, rightRoom: 8 });
		expect(t.ticks[0]).toEqual(starts[0]);
		expect(t.ticks.length).toBeLessThan(11);
		expect(t.ticks.length).toBeGreaterThan(2);
	});
});
