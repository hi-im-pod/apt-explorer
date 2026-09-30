<!--
	One chart: a legend, the plot, the counting rule beneath it, and the
	numbers as a table for anyone who cannot read the chart.

	The plot is drawn in the browser by the `plot` function, which gets the
	width to fill and the colours of the theme in effect. Colours are read
	from the CSS tokens at draw time, so the chart redraws whenever the theme
	store or the width changes. The theme store changes only after
	data-theme is set on <html>, so the tokens read are already the new
	theme's. Until the plot is drawn, which never happens without scripts,
	the chart's space is held and a line explains why it is empty.
-->
<script lang="ts" module>
	/** What a plot function gets: the width to fill and the theme's colours. */
	export interface ChartContext {
		width: number;
		/** --chart-1 to --chart-6, so series[0] is --chart-1. */
		series: string[];
		text: string;
		muted: string;
		/** Gridlines and the baseline. */
		grid: string;
		/** The page background the chart sits on. */
		background: string;
		/** The data font, for tick labels. */
		font: string;
	}

	export interface LegendItem {
		label: string;
		/** A colour token, such as "--chart-2". The swatch follows the theme through CSS. */
		token: string;
		/** A filled square for bars, or a short line for rules. */
		shape?: 'bar' | 'rule';
	}
</script>

<script lang="ts">
	import type { Snippet } from 'svelte';
	import { theme } from '$lib/theme';

	interface Props {
		/** What the chart shows, read by screen readers as the chart's name. */
		title: string;
		/** The counting rule, printed beneath the chart. */
		note: string;
		plot: (ctx: ChartContext) => SVGElement | HTMLElement;
		/** The height the plot draws at, held before it draws so nothing jumps. */
		height: number;
		/** Whether the x axis is time; the trends tests check such axes start in the window. */
		axis?: 'time' | 'value';
		legend?: LegendItem[];
		/** The chart's numbers as a table, shown under "Show the numbers". */
		table?: Snippet;
	}

	let { title, note, plot, height, axis = 'value', legend = [], table }: Props = $props();

	let box: HTMLDivElement;
	let width = $state(0);
	let drawn = $state(false);

	function context(w: number): ChartContext {
		const css = getComputedStyle(document.documentElement);
		const token = (name: string) => css.getPropertyValue(name).trim();
		return {
			width: w,
			series: [1, 2, 3, 4, 5, 6].map((n) => token(`--chart-${n}`)),
			text: token('--text'),
			muted: token('--text-muted'),
			grid: token('--border'),
			background: token('--bg'),
			font: token('--font-data') || 'monospace'
		};
	}

	$effect(() => {
		void $theme;
		const w = Math.floor(width);
		if (!box || w <= 0) return;
		box.replaceChildren(plot(context(w)));
		drawn = true;
	});
</script>

<div class="chart">
	<figure data-x={axis}>
		{#if legend.length}
			<ul class="legend">
				{#each legend as item (item.label)}
					<li>
						<span class="key {item.shape ?? 'bar'}" style:--key="var({item.token})" aria-hidden="true"
						></span>{item.label}
					</li>
				{/each}
			</ul>
		{/if}
		<div class="frame" style:min-height="{height}px">
			<div class="plot" role="img" aria-label={title} bind:this={box} bind:clientWidth={width}></div>
			{#if !drawn}
				<p class="fallback">This chart is drawn in your browser and needs scripts.</p>
			{/if}
		</div>
		<figcaption class="note">{note}</figcaption>
	</figure>
	{#if table}
		<details class="numbers">
			<summary>Show the numbers</summary>
			<div class="scroll">{@render table()}</div>
		</details>
	{/if}
</div>

<style>
	.chart {
		min-width: 0;
		/* Plot draws its tooltips on this colour. */
		--plot-background: var(--surface);
	}

	figure {
		margin: 0;
	}

	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 1.25rem;
		margin: 0 0 0.75rem;
		padding: 0;
		list-style: none;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.legend li {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
	}

	.key {
		flex: none;
		background: var(--key);
	}

	.key.bar {
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 1px;
	}

	.key.rule {
		width: 1rem;
		height: 2px;
	}

	.frame {
		position: relative;
	}

	.plot {
		width: 100%;
		min-width: 0;
		overflow: hidden;
	}

	.plot :global(svg) {
		display: block;
		max-width: 100%;
		height: auto;
	}

	.fallback {
		position: absolute;
		inset: 0;
		display: grid;
		place-items: center;
		margin: 0;
		padding: 1rem;
		border: 1px solid var(--border);
		border-radius: 0.375rem;
		color: var(--text-muted);
		font-size: 0.9375rem;
		text-align: center;
	}

	.note {
		max-width: 68ch;
		margin-top: 0.75rem;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.numbers {
		margin-top: 0.75rem;
		font-size: 0.875rem;
	}

	.numbers summary {
		width: fit-content;
		color: var(--accent);
		cursor: pointer;
	}

	/* A wide table scrolls inside its own box, never the page. */
	.scroll {
		max-width: 100%;
		overflow-x: auto;
		margin-top: 0.5rem;
	}
</style>
