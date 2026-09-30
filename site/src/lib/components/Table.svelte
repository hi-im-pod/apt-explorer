<!--
	The explore table: one row per report or campaign.

	It is an ARIA table built from divs rather than <table>, because on a
	narrow screen each row turns into a card, and changing the display of
	table elements makes some browsers drop their table semantics.

	Long lists are windowed: only the rows near the viewport are in the DOM,
	with padding standing in for the rest, so a build with tens of thousands
	of reports scrolls as smoothly as one with fifty. Every row has the same
	fixed height (set in CSS for each layout), which is what lets a scroll
	position map straight to a row index. Short lists render in full, so
	find-in-page and assistive technology see every row.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import type { ExploreRow } from '$lib/search';
	import { sourceLabel } from '$lib/data/labels';
	import { formatDate } from '$lib/format';
	import { describeLinks } from '$lib/links';

	interface Props {
		rows: ExploreRow[];
		/** Actor ID to display name. An ID missing here is shown as itself. */
		actorNames: ReadonlyMap<string, string>;
		/** The row whose details are open, if any. */
		selectedKey: string | null;
		/** The actor the view is filtered to; its chip is listed first. */
		actorFilter: string | null;
		/** The link that opens a row's details, so it can open in a new tab too. */
		hrefFor: (row: ExploreRow) => string;
		/** Called instead of following the link, with the link for focus return. */
		onopen: (row: ExploreRow, link: HTMLAnchorElement) => void;
	}

	let { rows, actorNames, selectedKey, actorFilter, hrefFor, onopen }: Props = $props();

	/** Below this many rows everything is rendered; windowing only pays off above it. */
	const WINDOW_FROM = 200;
	/** Rows rendered above and below the viewport, so a fast scroll never shows a gap. */
	const BUFFER = 12;
	/** Rows to render before the row height has been measured. */
	const FIRST_PAINT = 40;
	/** At most this many actor chips; the rest are counted. */
	const MAX_CHIPS = 3;

	let body: HTMLDivElement;
	let rowHeight = $state(0);
	/** How far the viewport's top edge is below the top of the table body, in px. */
	let viewTop = $state(0);
	let viewHeight = $state(900);

	const windowed = $derived(rows.length > WINDOW_FROM);
	const start = $derived.by(() => {
		if (!windowed || rowHeight === 0) return 0;
		const first = Math.floor(viewTop / rowHeight) - BUFFER;
		return Math.max(0, Math.min(first, rows.length - 1));
	});
	const end = $derived.by(() => {
		if (!windowed) return rows.length;
		if (rowHeight === 0) return Math.min(rows.length, FIRST_PAINT);
		const last = Math.ceil((viewTop + viewHeight) / rowHeight) + BUFFER;
		return Math.max(start, Math.min(last, rows.length));
	});
	const visible = $derived(rows.slice(start, end));

	/** Read the scroll position and the row height, at most once a frame. */
	let pending = false;
	function measure() {
		if (pending) return;
		pending = true;
		requestAnimationFrame(() => {
			pending = false;
			if (!body) return;
			viewTop = -body.getBoundingClientRect().top;
			viewHeight = window.innerHeight;
			// The row height changes with the layout (table or cards), so it is
			// re-read on every resize rather than cached from the first paint.
			const row = body.querySelector<HTMLElement>('[role="row"]');
			if (row) rowHeight = row.getBoundingClientRect().height;
		});
	}

	onMount(() => {
		measure();
		window.addEventListener('scroll', measure, { passive: true });
		window.addEventListener('resize', measure);
		return () => {
			window.removeEventListener('scroll', measure);
			window.removeEventListener('resize', measure);
		};
	});

	// A new filter can shrink the list under the viewport, so re-measure.
	$effect(() => {
		void rows;
		measure();
	});

	function chips(row: ExploreRow): { names: string[]; more: number } {
		const ids =
			actorFilter && row.actors.includes(actorFilter)
				? [actorFilter, ...row.actors.filter((a) => a !== actorFilter)]
				: row.actors;
		const names = ids.slice(0, MAX_CHIPS).map((id) => actorNames.get(id) ?? id);
		return { names, more: Math.max(0, ids.length - MAX_CHIPS) };
	}

	function sources(row: ExploreRow): string {
		return row.sources.map((s) => sourceLabel(s).short).join(', ');
	}

	// O: link cell start. A report's links, each named by kind, so a mirror
	// is never mistaken for the publisher. Campaigns have no links.
	function rowLinks(row: ExploreRow) {
		return row.report ? describeLinks(row.report).links : [];
	}
	// O: link cell end

	function click(e: MouseEvent, row: ExploreRow) {
		// A modified click keeps the browser's own behaviour, such as opening
		// the details in a new tab.
		if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
		e.preventDefault();
		onopen(row, e.currentTarget as HTMLAnchorElement);
	}
</script>

<div
	class="table"
	role="table"
	aria-label="Reports and campaigns"
	aria-rowcount={rows.length + 1}
	data-sveltekit-preload-data="false"
>
	<div class="head" role="rowgroup">
		<div class="row" role="row" aria-rowindex={1}>
			<span role="columnheader">Date</span>
			<span role="columnheader">Title</span>
			<span role="columnheader">Actors</span>
			<span role="columnheader">Source</span>
		</div>
	</div>
	<div
		class="body"
		role="rowgroup"
		bind:this={body}
		style:padding-top="{start * rowHeight}px"
		style:padding-bottom="{(rows.length - end) * rowHeight}px"
	>
		{#each visible as row, i (row.key)}
			{@const c = chips(row)}
			<div
				class="row"
				class:selected={row.key === selectedKey}
				role="row"
				aria-rowindex={start + i + 2}
			>
				<span class="date" role="cell">
					{#if row.date == null}
						<span class="undated">Undated</span>
					{:else if row.kind === 'campaign'}
						<time datetime={row.date}>{formatDate(row.date)}</time>
						<span class="until"
							>{#if row.end}to <time datetime={row.end}>{formatDate(row.end)}</time
								>{:else}end not reported{/if}</span
						>
					{:else}
						<time datetime={row.date}>{formatDate(row.date)}</time>
					{/if}
				</span>
				<span class="title" role="cell">
					{#if row.kind === 'campaign'}<span class="tag">Campaign</span>{/if}
					<a href={hrefFor(row)} onclick={(e) => click(e, row)}>{row.title}</a>
				</span>
				<span class="actors" role="cell">
					{#if c.names.length}
						<ul>
							{#each c.names as name (name)}<li>{name}</li>{/each}
							{#if c.more}<li class="more">+{c.more} more</li>{/if}
						</ul>
					{:else}
						<span class="none">No actor linked</span>
					{/if}
				</span>
				<span class="source" role="cell">{sources(row)}</span>
				<!-- O: link cell start -->
				<span class="links" role="cell">
					{#each rowLinks(row) as link (link.href)}
						<a
							href={link.href}
							class:copy={link.role === 'copy'}
							class:dead={link.unreachable}
							rel="noopener noreferrer"
							target="_blank"
							title="{link.class.label}: {link.class.explanation}"
							aria-label="{link.class.label}, {link.class.host}{link.unreachable
								? ', unreachable at last check'
								: ''}">{link.class.short}</a
						>
					{/each}
				</span>
				<!-- O: link cell end -->
			</div>
		{/each}
	</div>
</div>

<style>
	.table {
		/* Each layout fixes the row height; the windowing reads it back. */
		--row-h: 9.75rem;
		font-size: 0.9375rem;
	}

	/* Narrow screens: the header row is kept for screen readers but moved
	   off-screen, since each card labels its own parts by position. */
	.head {
		position: absolute;
		left: -10000px;
		width: 1px;
		height: 1px;
		overflow: hidden;
	}

	.row {
		position: relative;
		isolation: isolate;
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		grid-template-areas:
			'date source'
			'title title'
			'actors actors'
			'links links';
		align-content: start;
		gap: 0.25rem 0.75rem;
		height: var(--row-h);
		overflow: hidden;
		padding: 0.75rem 0.875rem 1.25rem;
	}

	/* The card face sits behind the row and stops short of the next card, so
	   the gap between cards is part of the fixed row height. */
	.body .row::before {
		content: '';
		position: absolute;
		inset: 0 0 0.5rem;
		z-index: -1;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 0.625rem;
	}

	.body .row:hover::before,
	.body .row:has(a:focus-visible)::before {
		border-color: var(--accent);
	}

	.body .row.selected::before {
		border-color: var(--accent);
		background: var(--accent-soft);
	}

	.date {
		grid-area: date;
		color: var(--text-muted);
		font-size: 0.8125rem;
		line-height: 1.4;
	}

	.until {
		margin-left: 0.25rem;
	}

	.undated {
		font-style: italic;
	}

	.source {
		grid-area: source;
		color: var(--text-muted);
		font-size: 0.8125rem;
		line-height: 1.4;
		text-align: right;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 11rem;
	}

	.title {
		grid-area: title;
		line-height: 1.4;
		font-weight: 550;
		/* Two lines at most, so every row has the same height. */
		display: -webkit-box;
		-webkit-line-clamp: 2;
		line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		overflow-wrap: break-word;
	}

	.title a {
		color: var(--text);
		text-decoration: none;
	}

	/* The whole row opens the details, not only the title's text. */
	.title a::after {
		content: '';
		position: absolute;
		inset: 0;
	}

	.title a:focus-visible {
		outline: none;
	}

	.title a:hover {
		color: var(--accent);
	}

	.tag {
		display: inline-block;
		margin-right: 0.375rem;
		padding: 0 0.375rem;
		border: 1px solid var(--accent-2);
		border-radius: 0.25rem;
		color: var(--accent-2);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		font-weight: 500;
		letter-spacing: 0.04em;
		line-height: 1.5;
		text-transform: uppercase;
		vertical-align: 0.1em;
	}

	.actors {
		grid-area: actors;
		min-width: 0;
	}

	.actors ul {
		display: flex;
		flex-wrap: nowrap;
		gap: 0.375rem;
		margin: 0;
		padding: 0;
		list-style: none;
		overflow: hidden;
	}

	.actors li {
		flex: none;
		max-width: 100%;
		padding: 0.0625rem 0.5rem;
		border-radius: 999px;
		background: var(--accent-soft);
		color: var(--text);
		font-size: 0.8125rem;
		line-height: 1.5;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.actors li.more {
		background: none;
		color: var(--text-muted);
		padding-inline: 0.125rem;
	}

	.none {
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	/* O: link cell styles. The links sit above the row-wide overlay that
	   opens the details, so a click on one follows the link instead. */
	.links {
		grid-area: links;
		display: flex;
		flex-wrap: nowrap;
		gap: 0.25rem 0.875rem;
		min-width: 0;
		overflow: hidden;
		font-size: 0.75rem;
		line-height: 1.5;
		white-space: nowrap;
	}

	.links a {
		position: relative;
		z-index: 1;
		color: var(--accent);
		font-weight: 600;
		text-decoration: underline;
		text-underline-offset: 0.15em;
	}

	/* A copy is not the publisher, so it is drawn quieter and dotted. */
	.links a.copy {
		color: var(--text-muted);
		font-weight: 500;
		text-decoration-style: dotted;
	}

	.links a.dead {
		text-decoration-line: line-through;
	}
	/* O: link cell styles end */

	/* Wide screens: a real table layout with a sticky header. */
	@media (min-width: 45rem) {
		.table {
			--row-h: 5.75rem;
		}

		.head {
			position: sticky;
			top: 0;
			left: auto;
			z-index: 2;
			width: auto;
			height: auto;
			overflow: visible;
			background: var(--bg);
			border-bottom: 1px solid var(--border);
		}

		.row {
			grid-template-columns: 10.5rem minmax(0, 1fr) minmax(0, 15rem) 8rem;
			grid-template-areas:
				'date title actors source'
				'date links actors source';
			grid-template-rows: auto 1fr;
			align-items: start;
			gap: 0 1.25rem;
			padding: 0.75rem 0.75rem;
		}

		.head .row {
			height: auto;
			padding-block: 0.5rem;
			color: var(--text-muted);
			font-family: var(--font-data);
			font-size: 0.6875rem;
			letter-spacing: 0.06em;
			text-transform: uppercase;
		}

		.body .row {
			border-bottom: 1px solid var(--border);
		}

		.body .row::before {
			inset: 0;
			border: 0;
			border-radius: 0;
			background: transparent;
		}

		.body .row:hover::before,
		.body .row:has(a:focus-visible)::before {
			background: var(--accent-soft);
		}

		.body .row:has(a:focus-visible) {
			outline: 2px solid var(--focus);
			outline-offset: -2px;
		}

		.body .row.selected::before {
			background: var(--accent-soft);
			box-shadow: inset 3px 0 0 var(--accent);
		}

		.until {
			display: block;
			margin-left: 0;
		}

		.source {
			text-align: left;
			white-space: normal;
			max-width: none;
		}

		.actors ul {
			flex-wrap: wrap;
			max-height: 3.25rem;
		}
	}
</style>
