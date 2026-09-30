<!--
	Exploited vulnerabilities and the actors named in the same reports, one
	page at a time.

	It is built like the explore table: an ARIA table of divs whose rows become
	cards on a narrow screen, with the same page controls above and below. A
	long actor list shows its first names as chips and keeps the rest inside a
	native <details>, so every name is in the page for find-in-page and
	assistive technology, and nothing scrolls sideways.
-->
<script lang="ts">
	import { base } from '$app/paths';
	import Pagination from '$lib/components/Pagination.svelte';
	import type { KevActorLink } from '$lib/data/types';
	import { DEFAULT_SIZE, clampPage, pageCount, pageOfIndex } from '$lib/paging';

	interface Props {
		links: KevActorLink[];
		/** Actor ID to display name. An ID missing here is shown as itself. */
		names: Record<string, string>;
	}

	let { links, names }: Props = $props();

	/** At most this many chips show before the rest fold away. */
	const MAX_CHIPS = 4;

	let page = $state(1);
	let size = $state(DEFAULT_SIZE);
	let frame = $state<HTMLElement>();

	const pages = $derived(pageCount(links.length, size));
	const current = $derived(clampPage(page, links.length, size));
	const offset = $derived((current - 1) * size);
	const rows = $derived(links.slice(offset, offset + size));

	function keepTopInView() {
		// The bottom controls change the page under the reader's thumb, so bring the new top into view.
		if (frame && frame.getBoundingClientRect().top < 0) frame.scrollIntoView({ block: 'start' });
	}

	function goToPage(n: number) {
		page = clampPage(n, links.length, size);
		keepTopInView();
	}

	function setSize(n: number) {
		page = pageOfIndex(offset, n);
		size = n;
	}

	const name = (id: string) => names[id] ?? id;
</script>

<div class="frame" bind:this={frame}>
	<Pagination
		position="top"
		page={current}
		count={pages}
		{size}
		total={links.length}
		all
		onpage={goToPage}
		onsize={setSize}
	/>
	<div
		class="table"
		role="table"
		aria-label="Exploited vulnerabilities and the actors named with them"
		aria-rowcount={links.length + 1}
		data-sveltekit-preload-data="false"
	>
		<div class="head" role="rowgroup">
			<div class="row" role="row" aria-rowindex={1}>
				<span role="columnheader">CVE</span>
				<span role="columnheader">Actors named in the same reports</span>
			</div>
		</div>
		<div class="body" role="rowgroup">
			{#each rows as l, i (l.cve)}
				{@const first = l.actors.slice(0, MAX_CHIPS)}
				{@const rest = l.actors.slice(MAX_CHIPS)}
				<div class="row" role="row" aria-rowindex={offset + i + 2}>
					<span class="cve" role="cell">
						<a href="{base}/explore/?cve={l.cve}">{l.cve}</a>
					</span>
					<span class="actors" role="cell">
						<ul>
							{#each first as id (id)}<li>{name(id)}</li>{/each}
						</ul>
						{#if rest.length}
							<details>
								<summary>{rest.length} more</summary>
								<ul>
									{#each rest as id (id)}<li>{name(id)}</li>{/each}
								</ul>
							</details>
						{/if}
					</span>
				</div>
			{/each}
		</div>
	</div>
	<Pagination
		position="bottom"
		page={current}
		count={pages}
		{size}
		total={links.length}
		all
		onpage={goToPage}
		onsize={setSize}
	/>
</div>

<style>
	.frame {
		overflow: hidden;
		border: 1px solid var(--border);
		border-radius: 0.5rem;
		background: var(--surface);
	}

	.table {
		font-size: 0.9375rem;
	}

	/* Narrow screens: the header row stays for screen readers but moves
	   off-screen, since each card names its own parts by position. */
	.head {
		position: absolute;
		left: -10000px;
		width: 1px;
		height: 1px;
		overflow: hidden;
	}

	.row {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 0.375rem;
		padding: 0.75rem 0.875rem;
	}

	.body .row {
		border-bottom: 1px solid var(--border);
	}

	.body .row:last-child {
		border-bottom: 0;
	}

	.body .row:hover {
		background: var(--accent-soft);
	}

	.cve a {
		color: var(--accent);
		font-family: var(--font-data);
		font-size: 0.875rem;
		font-weight: 500;
		overflow-wrap: anywhere;
	}

	.actors {
		min-width: 0;
	}

	ul {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	li {
		max-width: 100%;
		padding: 0.0625rem 0.5rem;
		border-radius: 999px;
		background: var(--accent-soft);
		color: var(--text);
		font-size: 0.8125rem;
		line-height: 1.5;
		overflow-wrap: anywhere;
	}

	.body .row:hover li {
		background: var(--surface);
	}

	details {
		margin-top: 0.375rem;
	}

	summary {
		display: inline-block;
		padding: 0.125rem 0;
		color: var(--text-muted);
		font-size: 0.8125rem;
		cursor: pointer;
	}

	summary:hover {
		color: var(--accent);
	}

	summary:focus-visible,
	a:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 2px;
	}

	details ul {
		margin-top: 0.375rem;
	}

	/* Wide screens: two columns and a sticky header. */
	@media (min-width: 45rem) {
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
			grid-template-columns: 10rem minmax(0, 1fr);
			align-items: start;
			gap: 0 1.25rem;
			padding: 0.75rem 0.75rem;
		}

		.head .row {
			padding-block: 0.5rem;
			color: var(--text-muted);
			font-family: var(--font-data);
			font-size: 0.6875rem;
			letter-spacing: 0.06em;
			text-transform: uppercase;
		}
	}
</style>
