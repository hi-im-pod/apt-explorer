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

/** The tooltip's look, so it matches the page in every theme. */
function tipStyle(ctx: ChartContext) {
	return { fill: ctx.background, stroke: ctx.grid, fontSize: 12, textPadding: 8 };
}

/** Integer ticks only: counts have no halves. */
const countTick = (d: number) => (Number.isInteger(d) ? formatCount(d) : '');

// ---------------------------------------------------------------------------
// Reporting activity: one small chart per actor, sharing one time axis.

// Each small chart is 84px: a 24px name line, then a plot tall enough to compare neighbouring bars.
const FACET = 84;
const ACTIVITY_MARGINS = { marginTop: 4, marginRight: 8, marginBottom: 28, marginLeft: 32 };

export function activityHeight(actors: number): number {
	return actors * FACET + ACTIVITY_MARGINS.marginTop + ACTIVITY_MARGINS.marginBottom;
}

export function activityChart(a: Activity, names: Record<string, string>) {
	return (ctx: ChartContext) => {
		const from = a.points[0].start;
		const to = a.points[a.points.length - 1].end;
		const plotWidth = ctx.width - ACTIVITY_MARGINS.marginLeft - ACTIVITY_MARGINS.marginRight;
		const inset = barInset(plotWidth / a.quarters.length);
		const quarterStarts = a.points.filter((p) => p.actor === a.actors[0]).map((p) => p.start);
		const { ticks, format } = pickTicks(quarterStarts, 'quarter', {
			plotWidth,
			leftRoom: ACTIVITY_MARGINS.marginLeft,
			rightRoom: ACTIVITY_MARGINS.marginRight
		});
		const top = Math.max(1, ...a.points.map((p) => Math.max(p.count, p.prev)));
		const name = (id: string) => names[id] ?? id;
		const tip = (p: Activity['points'][number]) =>
			`${name(p.actor)}, ${quarterName(p.quarter)}\n${plural(p.count, 'report', 'reports')}\n${plural(p.prev, 'report', 'reports')} a year earlier`;

		return Plot.plot({
			...frame(ctx, activityHeight(a.actors.length), ACTIVITY_MARGINS),
			fy: { domain: a.actors, axis: null, padding: 0 },
			x: { type: 'utc', domain: [from, to], ticks, tickFormat: format, label: null },
			// The top of each small chart is kept free for the actor's name.
			y: { domain: [0, top], insetTop: 24, label: null, ticks: [top], tickFormat: countTick, tickSize: 0 },
			marks: [
				Plot.gridY({ ticks: [top], stroke: ctx.grid, strokeOpacity: 1 }),
				Plot.ruleY([0], { stroke: ctx.grid }),
				Plot.rectY(
					a.points.filter((p) => p.count > 0),
					{
						fy: 'actor',
						x1: 'start',
						x2: 'end',
						y: 'count',
						fill: ctx.series[1],
						insetLeft: inset,
						insetRight: inset,
						ry2: 3
					}
				),
				// The same quarter a year earlier, as a short line across the bar's slot.
				Plot.ruleY(
					a.points.filter((p) => p.prev > 0),
					{
						fy: 'actor',
						x1: 'start',
						x2: 'end',
						y: 'prev',
						stroke: ctx.text,
						strokeWidth: 2,
						strokeLinecap: 'round',
						insetLeft: Math.max(0, inset - 3),
						insetRight: Math.max(0, inset - 3)
					}
				),
				Plot.text(a.actors, {
					fy: (d: string) => d,
					frameAnchor: 'top-left',
					text: name,
					fill: ctx.text,
					fontSize: 12,
					fontWeight: 600,
					dy: 4
				}),
				Plot.tip(
					a.points,
					Plot.pointerX({ fy: 'actor', x: midpoint, y: 'count', title: tip, ...tipStyle(ctx) })
				)
			]
		});
	};
}

// ---------------------------------------------------------------------------
// KEV additions per month, split by known ransomware use.

export const KEV_HEIGHT = 260;
const KEV_MARGINS = { marginTop: 12, marginRight: 8, marginBottom: 28, marginLeft: 36 };

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

		return Plot.plot({
			...frame(ctx, KEV_HEIGHT, KEV_MARGINS),
			x: { type: 'utc', domain: [from, to], ticks, tickFormat: format, label: null },
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
				Plot.ruleY([0], { stroke: ctx.grid }),
				Plot.tip(k, Plot.pointerX({ x: midpoint, y: 'added', title: tip, ...tipStyle(ctx) }))
			]
		});
	};
}

// ---------------------------------------------------------------------------
// Reported versus documented techniques: one bar per actor, name above it.

const ROW = 40;
const TECH_MARGINS = { marginTop: 4, marginRight: 16, marginBottom: 28, marginLeft: 4 };

export function techniqueHeight(actors: number): number {
	return actors * ROW + TECH_MARGINS.marginTop + TECH_MARGINS.marginBottom;
}

export function techniqueChart(bars: TechniqueBar[], names: Record<string, string>) {
	return (ctx: ChartContext) => {
		const total = (b: TechniqueBar) => b.overlap + b.reportedOnly;
		const name = (b: TechniqueBar) => names[b.actor] ?? b.actor;
		const tip = (b: TechniqueBar) =>
			`${name(b)}\n${plural(b.reportedOnly, 'technique', 'techniques')} reported only` +
			(b.ids.length ? `: ${b.ids.join(', ')}` : '') +
			`\n${plural(b.overlap, 'technique', 'techniques')} also documented by ATT&CK`;
		// Each row is 40px: the name on top, a 12px bar below it.
		const bar = { y: 'actor', insetTop: 22, insetBottom: 6 } as const;

		return Plot.plot({
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
				}),
				Plot.tip(bars, Plot.pointerY({ y: 'actor', x: total, title: tip, ...tipStyle(ctx) }))
			]
		});
	};
}

// ---------------------------------------------------------------------------
// Newly documented actors per month: a small chart beside the list.

export const NEW_ACTORS_HEIGHT = 180;
// The left margin is wide enough for a first label such as "Oct 2025", which is centred on the axis start.
const NEW_MARGINS = { marginTop: 8, marginRight: 12, marginBottom: 28, marginLeft: 40 };

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

		return Plot.plot({
			...frame(ctx, NEW_ACTORS_HEIGHT, NEW_MARGINS),
			x: { type: 'utc', domain: [from, to], ticks, tickFormat: format, label: null },
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
				Plot.ruleY([0], { stroke: ctx.grid }),
				Plot.tip(months, Plot.pointerX({ x: midpoint, y: 'count', title: tip, ...tipStyle(ctx) }))
			]
		});
	};
}
