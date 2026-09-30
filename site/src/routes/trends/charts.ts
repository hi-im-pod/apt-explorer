/**
 * The trends charts, drawn with Observable Plot.
 *
 * Each builder takes a prepared series (see series.ts) and returns the plot
 * function Chart.svelte calls with the width and the theme's colours. The
 * drawing follows a few fixed rules so the charts read as one set:
 *
 * - Bars are at most 24px thick, with a 2px gap in the background colour
 *   between neighbours and between stacked parts, and rounded only at the
 *   data end.
 * - Gridlines and baselines are 1px in the border colour; text uses the text
 *   tokens, never a series colour.
 * - Time axes run from exactly the first period of the series, which is
 *   never before window_start, with a tick labelled with its year there.
 * - Hovering shows a tooltip with the exact numbers; the same numbers are in
 *   each chart's table, so the tooltip is never the only way to read them.
 */
import * as Plot from '@observablehq/plot';
import type { ChartContext } from '$lib/components/Chart.svelte';
import { formatCount, formatDate } from '$lib/format';
import type { Activity, KevPoint, MonthCount, TechniqueBar } from './series';
import { pickTicks } from './ticks';
import { nearestSlot, withTooltip, type Pick } from './tooltip';

const BAR_MAX = 24;
// 12px keeps tick labels readable on a phone. ticks.ts assumes this size when it spaces them.
const TICK_FONT = '12px';

/** Side insets that keep a bar in a slot of `slot` px at most BAR_MAX wide, with a 2px gap. */
function barInset(slot: number): number {
	return Math.max(1, (slot - BAR_MAX) / 2);
}

const midpoint = (p: { start: Date; end: Date }) =>
	new Date((p.start.getTime() + p.end.getTime()) / 2);

/** "2024-05" to "May 2024". */
function monthName(month: string): string {
	return formatDate(`${month}-01`).replace(/^1 /, '');
}

/** "2024-Q2" to "Q2 2024". */
function quarterName(quarter: string): string {
	return `${quarter.slice(5)} ${quarter.slice(0, 4)}`;
}

const plural = (n: number, one: string, many: string) => `${formatCount(n)} ${n === 1 ? one : many}`;

/** Options every chart shares: its size, font and the colour of its axis text. */
function frame(ctx: ChartContext, height: number, margins: Record<string, number>) {
	return {
		width: ctx.width,
		height,
		...margins,
		style: {
			background: 'transparent',
			color: ctx.muted,
			fontFamily: ctx.font,
			fontSize: TICK_FONT,
			overflow: 'visible'
		}
	};
}

interface Margins {
	marginTop: number;
	marginRight: number;
	marginBottom: number;
	marginLeft: number;
}

type Scale = { apply(value: unknown): number } | undefined;
type Scaled = Element & { scale(name: string): Scale };

/** Reads px positions back from a drawn plot, so the tooltip uses exactly the geometry Plot drew. */
function positions(svg: Element) {
	const x = (svg as Scaled).scale('x');
	const y = (svg as Scaled).scale('y');
	return {
		x: (d: Date | number) => x!.apply(d),
		y: (v: number) => y!.apply(v)
	};
}

/**
 * Tooltip picking for a bar chart over time: the bar whose slot is nearest
 * to the pointer, with the plot area as the only place that answers.
 */
function timePick<T extends { start: Date; end: Date }>(
	svg: Element,
	ctx: ChartContext,
	m: Margins,
	height: number,
	points: T[],
	bar: { value: (p: T) => number; inset: number; text: (p: T) => string }
): Pick {
	const at = positions(svg);
	const slots = points.map((p) => [at.x(p.start), at.x(p.end)] as [number, number]);
	const base = at.y(0);
	return (px, py) => {
		if (px < m.marginLeft || px > ctx.width - m.marginRight) return null;
		if (py < m.marginTop || py > height - m.marginBottom) return null;
		const i = nearestSlot(slots, px);
		const [a, b] = slots[i];
		const top = at.y(bar.value(points[i]));
		return {
			text: bar.text(points[i]),
			box: {
				x: a + bar.inset,
				y: Math.min(top, base - 2),
				w: Math.max(2, b - a - 2 * bar.inset),
				h: Math.max(2, base - top)
			}
		};
	};
}

/** Integer ticks only: counts have no halves. */
const countTick = (d: number) => (Number.isInteger(d) ? formatCount(d) : '');

// ---------------------------------------------------------------------------
// Reporting activity: a heatmap with one row per actor and one column per quarter.

// Each row is 48px: a name line on top, then a 24px cell that holds the count.
const ROW = 48;
const CELL_TOP = 22;
const CELL_BOTTOM = 2;
const ACTIVITY_MARGINS = { marginTop: 4, marginRight: 8, marginBottom: 32, marginLeft: 32 };
/** The faintest a quarter with reports is drawn; a quarter with none is fainter still. */
const OPACITY_MIN = 0.22;
const OPACITY_NONE = 0.07;

export function activityHeight(actors: number): number {
	return actors * ROW + ACTIVITY_MARGINS.marginTop + ACTIVITY_MARGINS.marginBottom;
}

type Rgb = [number, number, number];

const hexRgb = (hex: string): Rgb | null => {
	const m = /^#([0-9a-f]{6})$/i.exec(hex.trim());
	if (!m) return null;
	const n = parseInt(m[1], 16);
	return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

const luminance = ([r, g, b]: Rgb) => {
	const lin = (c: number) => {
		const v = c / 255;
		return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
	};
	return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
};

const contrast = (a: number, b: number) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);

/** The text colour that reads best on the series colour drawn at `opacity` over the page background. */
function inkOn(ctx: ChartContext, opacity: number): string {
	const fill = hexRgb(ctx.series[1]);
	const page = hexRgb(ctx.background);
	const ink = hexRgb(ctx.text);
	if (!fill || !page || !ink) return ctx.text;
	const blended = fill.map((c, i) => c * opacity + page[i] * (1 - opacity)) as Rgb;
	const under = luminance(blended);
	return contrast(luminance(ink), under) >= contrast(luminance(page), under) ? ctx.text : ctx.background;
}

export function activityChart(a: Activity, names: Record<string, string>) {
	return (ctx: ChartContext) => {
		type Point = Activity['points'][number];
		const from = a.points[0].start;
		const to = a.points[a.points.length - 1].end;
		const height = activityHeight(a.actors.length);
		const plotWidth = ctx.width - ACTIVITY_MARGINS.marginLeft - ACTIVITY_MARGINS.marginRight;
		const inset = 1;
		const quarterStarts = a.points.filter((p) => p.actor === a.actors[0]).map((p) => p.start);
		// Each label sits under the middle of its column, half a column right of the period start,
		// so the right-hand room shrinks by the same half column.
		const pitch = plotWidth / quarterStarts.length;
		const picked = pickTicks(quarterStarts, 'quarter', {
			plotWidth,
			leftRoom: ACTIVITY_MARGINS.marginLeft,
			rightRoom: ACTIVITY_MARGINS.marginRight - pitch / 2
		});
		const columns = a.points.filter((p) => p.actor === a.actors[0]);
		const middleOf = new Map(columns.map((p) => [p.start.getTime(), midpoint(p)]));
		const ticks = picked.ticks.map((t) => middleOf.get(t.getTime()) ?? t);
		const startOf = new Map(picked.ticks.map((t, i) => [ticks[i].getTime(), t]));
		const format = (d: Date) => picked.format(startOf.get(d.getTime()) ?? d);
		const top = Math.max(1, ...a.points.map((p) => p.count));
		const name = (id: string) => names[id] ?? id;
		const opacity = (p: Point) =>
			p.count === 0 ? OPACITY_NONE : OPACITY_MIN + (1 - OPACITY_MIN) * Math.sqrt(p.count / top);
		const tip = (p: Point) =>
			`${name(p.actor)}, ${quarterName(p.quarter)}\n${plural(p.count, 'report', 'reports')}\n${plural(p.prev, 'report', 'reports')} a year earlier`;

		const svg = Plot.plot({
			...frame(ctx, height, ACTIVITY_MARGINS),
			y: { domain: a.actors, axis: null, padding: 0 },
			x: { type: 'utc', domain: [from, to], ticks, tickFormat: format, label: null, tickPadding: 8, tickSize: 4 },
			marks: [
				Plot.barX(a.points, {
					y: 'actor',
					x1: 'start',
					x2: 'end',
					fill: ctx.series[1],
					fillOpacity: opacity,
					insetTop: CELL_TOP,
					insetBottom: CELL_BOTTOM,
					insetLeft: inset,
					insetRight: inset,
					rx: 3
				}),
				// The count is written in the cell, so no reader has to judge a shade.
				Plot.text(
					a.points.filter((p) => p.count > 0),
					{
						y: 'actor',
						x: midpoint,
						text: (p: Point) => formatCount(p.count),
						dy: (CELL_TOP - CELL_BOTTOM) / 2,
						fill: (p: Point) => inkOn(ctx, opacity(p)),
						fontSize: 12,
						fontWeight: 600
					}
				),
				Plot.text(a.actors, {
					y: (d: string) => d,
					x: from,
					textAnchor: 'start',
					text: name,
					fill: ctx.text,
					fontSize: 12,
					fontWeight: 600,
					dy: 10 - ROW / 2
				})
			]
		});

		const at = positions(svg);
		const slots = a.points
			.filter((p) => p.actor === a.actors[0])
			.map((p) => [at.x(p.start), at.x(p.end)] as [number, number]);
		const byCell = new Map(a.points.map((p) => [`${p.actor} ${p.quarter}`, p]));
		const pick: Pick = (px, py) => {
			if (px < ACTIVITY_MARGINS.marginLeft || px > ctx.width - ACTIVITY_MARGINS.marginRight) return null;
			const y = py - ACTIVITY_MARGINS.marginTop;
			if (y < 0 || y >= a.actors.length * ROW) return null;
			const row = Math.floor(y / ROW);
			const col = nearestSlot(slots, px);
			const p = byCell.get(`${a.actors[row]} ${a.quarters[col]}`);
			if (!p) return null;
			const [x1, x2] = slots[col];
			return {
				text: tip(p),
				box: {
					x: x1 + inset,
					y: ACTIVITY_MARGINS.marginTop + row * ROW + CELL_TOP,
					w: x2 - x1 - 2 * inset,
					h: ROW - CELL_TOP - CELL_BOTTOM
				}
			};
		};
		return withTooltip(svg, ctx, pick);
	};
}

// ---------------------------------------------------------------------------
// KEV additions per month, split by known ransomware use.

export const KEV_HEIGHT = 260;
const KEV_MARGINS = { marginTop: 12, marginRight: 8, marginBottom: 32, marginLeft: 36 };

export function kevChart(k: KevPoint[]) {
	return (ctx: ChartContext) => {
		const from = k[0].start;
		const to = k[k.length - 1].end;
		const plotWidth = ctx.width - KEV_MARGINS.marginLeft - KEV_MARGINS.marginRight;
		const inset = barInset(plotWidth / k.length);
		const { ticks, format } = pickTicks(
			k.map((p) => p.start),
			'month',
			{ plotWidth, leftRoom: KEV_MARGINS.marginLeft, rightRoom: KEV_MARGINS.marginRight }
		);
		const tip = (p: KevPoint) => {
			const share = p.added ? Math.round((p.ransomware / p.added) * 100) : 0;
			return `${monthName(p.month)}\n${plural(p.added, 'CVE', 'CVEs')} added\n${formatCount(p.ransomware)} with known ransomware use (${share}%)`;
		};

		const svg = Plot.plot({
			...frame(ctx, KEV_HEIGHT, KEV_MARGINS),
			x: { type: 'utc', domain: [from, to], ticks, tickFormat: format, label: null, tickPadding: 8 },
			y: { nice: true, label: null, tickFormat: countTick, tickSize: 0 },
			marks: [
				Plot.gridY({ stroke: ctx.grid, strokeOpacity: 1 }),
				Plot.axisY({ tickFormat: countTick, tickSize: 0, label: null }),
				// Ransomware sits on the baseline, so its share is easy to compare
				// month to month; the 1px insets leave a 2px gap between the parts.
				Plot.rectY(
					k.filter((p) => p.ransomware > 0),
					{
						x1: 'start',
						x2: 'end',
						y1: 0,
						y2: 'ransomware',
						fill: ctx.series[3],
						insetLeft: inset,
						insetRight: inset,
						insetTop: 1
					}
				),
				Plot.rectY(
					k.filter((p) => p.other > 0),
					{
						x1: 'start',
						x2: 'end',
						y1: 'ransomware',
						y2: 'added',
						fill: ctx.series[1],
						insetLeft: inset,
						insetRight: inset,
						insetBottom: 1,
						ry2: 3
					}
				),
				Plot.ruleY([0], { stroke: ctx.grid })
			]
		});
	return withTooltip(
		svg,
		ctx,
		timePick(svg, ctx, KEV_MARGINS, KEV_HEIGHT, k, { value: (p) => p.added, inset, text: tip })
	);
	};
}

// ---------------------------------------------------------------------------
// Reported versus documented techniques: one bar per actor, name above it.

const TECH_ROW = 40;
const TECH_MARGINS = { marginTop: 4, marginRight: 16, marginBottom: 32, marginLeft: 4 };
const TECH_BAR_TOP = 22;
const TECH_BAR_BOTTOM = 6;

export function techniqueHeight(actors: number): number {
	return actors * TECH_ROW + TECH_MARGINS.marginTop + TECH_MARGINS.marginBottom;
}

export function techniqueChart(bars: TechniqueBar[], names: Record<string, string>) {
	return (ctx: ChartContext) => {
		const total = (b: TechniqueBar) => b.overlap + b.reportedOnly;
		const name = (b: TechniqueBar) => names[b.actor] ?? b.actor;
		// Counts only: the technique IDs are in the table under the chart.
		const tip = (b: TechniqueBar) =>
			`${name(b)}\n${plural(b.reportedOnly, 'technique', 'techniques')} reported only` +
			`\n${plural(b.overlap, 'technique', 'techniques')} also documented by ATT&CK`;
		// Each row is 40px: the name on top, a 12px bar below it.
		const bar = { y: 'actor', insetTop: TECH_BAR_TOP, insetBottom: TECH_BAR_BOTTOM } as const;

		const svg = Plot.plot({
			...frame(ctx, techniqueHeight(bars.length), TECH_MARGINS),
			y: { domain: bars.map((b) => b.actor), axis: null, padding: 0 },
			x: { nice: true, label: null, tickFormat: countTick, tickSize: 0 },
			marks: [
				Plot.gridX({ stroke: ctx.grid, strokeOpacity: 1 }),
				Plot.axisX({ tickFormat: countTick, tickSize: 0, label: null }),
				Plot.barX(
					bars.filter((b) => b.overlap > 0),
					{ ...bar, x1: 0, x2: 'overlap', fill: ctx.series[1], insetRight: 1 }
				),
				Plot.barX(
					bars.filter((b) => b.reportedOnly > 0),
					{ ...bar, x1: 'overlap', x2: total, fill: ctx.series[3], insetLeft: 1, rx2: 3 }
				),
				Plot.ruleX([0], { stroke: ctx.grid }),
				Plot.text(bars, {
					y: 'actor',
					x: 0,
					text: name,
					textAnchor: 'start',
					dy: -9,
					fill: ctx.text,
					fontSize: 12,
					fontWeight: 600
				})
			]
		});

	const at = positions(svg);
	const pick: Pick = (px, py) => {
		if (px < TECH_MARGINS.marginLeft || px > ctx.width - TECH_MARGINS.marginRight) return null;
		const y = py - TECH_MARGINS.marginTop;
		if (y < 0 || y >= bars.length * TECH_ROW) return null;
		const row = Math.floor(y / TECH_ROW);
		const b = bars[row];
		const x0 = at.x(0);
		return {
			text: tip(b),
			box: {
				x: x0,
				y: TECH_MARGINS.marginTop + row * TECH_ROW + TECH_BAR_TOP,
				w: Math.max(2, at.x(total(b)) - x0),
				h: TECH_ROW - TECH_BAR_TOP - TECH_BAR_BOTTOM
			}
		};
	};
	return withTooltip(svg, ctx, pick);
	};
}

// ---------------------------------------------------------------------------
// Newly documented actors per month: a small chart beside the list.

export const NEW_ACTORS_HEIGHT = 180;
// The left margin is wide enough for a first label such as "Oct 2025", which is centred on the axis start.
const NEW_MARGINS = { marginTop: 8, marginRight: 12, marginBottom: 32, marginLeft: 40 };

export function newActorsChart(months: MonthCount[]) {
	return (ctx: ChartContext) => {
		const from = months[0].start;
		const to = months[months.length - 1].end;
		const plotWidth = ctx.width - NEW_MARGINS.marginLeft - NEW_MARGINS.marginRight;
		const inset = barInset(plotWidth / months.length);
		const { ticks, format } = pickTicks(
			months.map((p) => p.start),
			'month',
			{ plotWidth, leftRoom: NEW_MARGINS.marginLeft, rightRoom: NEW_MARGINS.marginRight }
		);
		const tip = (p: MonthCount) => `${monthName(p.month)}\n${plural(p.count, 'new actor', 'new actors')}`;

		const svg = Plot.plot({
			...frame(ctx, NEW_ACTORS_HEIGHT, NEW_MARGINS),
			x: { type: 'utc', domain: [from, to], ticks, tickFormat: format, label: null, tickPadding: 8 },
			y: { nice: true, label: null, tickFormat: countTick, tickSize: 0 },
			marks: [
				Plot.gridY({ stroke: ctx.grid, strokeOpacity: 1 }),
				Plot.axisY({ tickFormat: countTick, tickSize: 0, label: null }),
				Plot.rectY(
					months.filter((p) => p.count > 0),
					{
						x1: 'start',
						x2: 'end',
						y: 'count',
						fill: ctx.series[1],
						insetLeft: inset,
						insetRight: inset,
						ry2: 3
					}
				),
				Plot.ruleY([0], { stroke: ctx.grid })
			]
		});
	return withTooltip(
		svg,
		ctx,
		timePick(svg, ctx, NEW_MARGINS, NEW_ACTORS_HEIGHT, months, { value: (p) => p.count, inset, text: tip })
	);
	};
}
