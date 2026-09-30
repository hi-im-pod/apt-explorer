<!--
	Reports per quarter as a column chart.

	The chart is plain HTML and CSS rather than a plotting library, so the
	prerendered page shows it with scripts blocked, and every colour is a
	theme token without a redraw when the theme changes. Columns share the
	width through minmax(0, 1fr), so a decade of quarters narrows the bars
	instead of widening the page.
-->
<script module lang="ts">
	import type { TimelinePoint } from '$lib/data';

	function parseQuarter(q: string): [number, number] {
		const m = /^(\d{4})-Q([1-4])$/.exec(q);
		if (!m) throw new Error(`Not a quarter: ${q}`);
		return [Number(m[1]), Number(m[2])];
	}

	/**
	 * Every quarter from the first point to the last, oldest first, with 0
	 * for the quarters the data leaves out. The data drops empty quarters to
	 * stay small, but a chart without them would draw a two-year silence as
	 * two neighbouring bars.
	 */
	export function fillQuarters(points: readonly TimelinePoint[]): TimelinePoint[] {
		if (points.length === 0) return [];
		const counts = new Map(points.map((p) => [p.quarter, p.count]));
		const sorted = [...counts.keys()].sort();
		let [y, q] = parseQuarter(sorted[0]);
		const [lastY, lastQ] = parseQuarter(sorted[sorted.length - 1]);
		const out: TimelinePoint[] = [];
		while (y < lastY || (y === lastY && q <= lastQ)) {
			const quarter = `${y}-Q${q}`;
			out.push({ quarter, count: counts.get(quarter) ?? 0 });
			if (q === 4) {
				y += 1;
				q = 1;
			} else q += 1;
		}
		return out;
	}
</script>

<script lang="ts">
	import { formatCount } from '$lib/format';

	interface Props {
		/** The actor's timeline as published: dated reports per quarter, empty quarters left out. */
		points: TimelinePoint[];
		/** Reports without a usable date, which no quarter can hold. */
		undated: number;
	}

	let { points, undated }: Props = $props();

	const columns = $derived(fillQuarters(points));
	const max = $derived(Math.max(1, ...columns.map((c) => c.count)));
	// Two pixels of surface between bars reads as separate bars; past about
	// forty columns at phone width that gap would eat most of the chart.
	const gap = $derived(columns.length > 40 ? '1px' : '2px');

	const label = (quarter: string) => quarter.replace('-', ' ');
	const reports = (n: number) => (n === 0 ? 'no reports' : n === 1 ? '1 report' : `${formatCount(n)} reports`);
</script>

{#if columns.length > 0}
	<figure class="timeline">
		<div class="chart">
			<div class="y" aria-hidden="true">
				<span class="data">{formatCount(max)}</span>
				<span class="data">0</span>
			</div>
			<div class="plot">
				<ol class="bars" style="--n: {columns.length}; --gap: {gap}" aria-label="Dated reports per quarter">
					{#each columns as c (c.quarter)}
						<li title="{label(c.quarter)}: {reports(c.count)}">
							{#if c.count > 0}
								<!-- The 2px floor keeps one report visible beside hundreds. -->
								<span class="bar" style="height: max(2px, {(c.count / max) * 100}%)"></span>
							{/if}
							<span class="visually-hidden">{label(c.quarter)}: {reports(c.count)}</span>
						</li>
					{/each}
				</ol>
				<div class="ticks" style="--n: {columns.length}; --gap: {gap}" aria-hidden="true">
					{#each columns as c (c.quarter)}
						<span class:year={c.quarter.endsWith('Q1')}></span>
					{/each}
				</div>
				<div class="ends" aria-hidden="true">
					<span class="data">{label(columns[0].quarter)}</span>
					{#if columns.length > 1}
						<span class="data">{label(columns[columns.length - 1].quarter)}</span>
					{/if}
				</div>
			</div>
		</div>
		<figcaption>
			Dated reports per quarter, {label(columns[0].quarter)} to {label(columns[columns.length - 1].quarter)}.
			A quarter without a bar had no dated report.
			{#if undated > 0}
				{undated === 1 ? '1 undated report is' : `${formatCount(undated)} undated reports are`} not shown.
			{/if}
		</figcaption>
	</figure>
{/if}

<style>
	.timeline {
		margin: 0;
		min-width: 0;
	}

	.chart {
		display: grid;
		grid-template-columns: auto minmax(0, 1fr);
		gap: 0.5rem;
	}

	.y {
		display: flex;
		flex-direction: column;
		justify-content: space-between;
		/* Matches the plot height, so the labels sit on the top line and the baseline. */
		height: 7.5rem;
		color: var(--text-muted);
		font-size: 0.6875rem;
		line-height: 1;
		text-align: right;
		font-variant-numeric: tabular-nums;
	}

	.plot {
		min-width: 0;
	}

	.bars,
	.ticks {
		display: grid;
		grid-template-columns: repeat(var(--n), minmax(0, 1fr));
		column-gap: var(--gap);
	}

	.bars {
		height: 7.5rem;
		margin: 0;
		padding: 0;
		list-style: none;
		/* The top line marks the peak, and the ink baseline grounds the bars. */
		border-top: 1px solid var(--grid);
		border-bottom: 1px solid var(--text);
	}

	.bars li {
		display: flex;
		align-items: flex-end;
		justify-content: center;
		min-width: 0;
	}

	.bar {
		display: block;
		width: min(100%, 24px);
		background: var(--accent);
	}

	.bars li:hover .bar {
		background: var(--text);
	}

	.ticks {
		height: 0.3125rem;
	}

	.ticks .year {
		border-left: 1px solid var(--border);
	}

	.ends {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 0.125rem;
		color: var(--text-muted);
		font-size: 0.6875rem;
		white-space: nowrap;
	}

	figcaption {
		margin-top: 0.75rem;
		color: var(--text-muted);
		font-size: 0.875rem;
	}
</style>
