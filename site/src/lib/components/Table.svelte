<!--
	The explore table: one row per report or campaign, for ONE page of the list.

	It is an ARIA table built from divs rather than <table>, because on a
	narrow screen each row turns into a card, and changing the display of
	table elements makes some browsers drop their table semantics.

	The page decides which rows to show, so every row here is in the DOM and
	find-in-page and assistive technology see all of them. `offset` is the
	number of rows on earlier pages, and `total` the rows on all pages, so the
	row indexes and count stay true to the whole list.
-->
<script lang="ts">
	import type { ExploreRow } from '$lib/search';
	import { sourceLabel } from '$lib/data/labels';
	import { formatDate } from '$lib/format';

	interface Props {
		/** The rows on this page. */
		rows: ExploreRow[];
		/** How many rows come before this page. */
		offset: number;
		/** How many rows there are across all pages. */
		total: number;
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

	let { rows, offset, total, actorNames, selectedKey, actorFilter, hrefFor, onopen }: Props = $props();

	/** At most this many actor chips; the rest are counted. */
	const MAX_CHIPS = 3;

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
	aria-rowcount={total + 1}
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
	<div class="body" role="rowgroup">
		{#each rows as row, i (row.key)}
			{@const c = chips(row)}
			<div
				class="row"
				class:selected={row.key === selectedKey}
				role="row"
				aria-rowindex={offset + i + 2}
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
			</div>
		{/each}
	</div>
</div>

<style>
	.table {
		/* Each layout fixes the row height, so a page is the same height whatever its titles say. */
		--row-h: 7.125rem;
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
			'actors actors';
		align-content: start;
		gap: 0.25rem 0.75rem;
		height: var(--row-h);
		overflow: hidden;
		padding: 0.75rem 0.875rem;
	}

	/* The row face sits behind the row so hover, focus and selection can tint it. */
	.body .row {
		border-bottom: 1px solid var(--border);
	}

	.body .row:last-child {
		border-bottom: 0;
	}

	.body .row::before {
		content: '';
		position: absolute;
		inset: 0;
		z-index: -1;
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

	/* The open row: soft pink and a 3px accent bar on its left edge. */
	.body .row.selected::before {
		background: var(--accent-soft);
		box-shadow: inset 3px 0 0 var(--accent);
	}

	.date {
		grid-area: date;
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.75rem;
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
		margin-right: 0.5rem;
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

	.row.selected .actors li {
		background: var(--surface);
	}

	.actors li.more,
	.row.selected .actors li.more {
		background: none;
		color: var(--text-muted);
		padding-inline: 0.125rem;
	}

	.none {
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	/* Wide screens: a real table layout with a sticky header. */
	@media (min-width: 45rem) {
		.table {
			--row-h: 4.25rem;
		}

		.head {
			position: sticky;
			top: 0;
			left: auto;
			z-index: 2;
			width: auto;
			height: auto;
			overflow: visible;
			background: var(--surface);
			border-bottom: 1px solid var(--border);
		}

		.row {
			grid-template-columns: 10.5rem minmax(0, 1fr) minmax(0, 15rem) 8rem;
			grid-template-areas: 'date title actors source';
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
