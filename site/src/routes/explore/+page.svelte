<!--
	Explore: every report and campaign in one filterable table.

	The page is prerendered as a shell, and the rows load in the browser.
	Loading them in a prerendered load function would inline every report
	shard into the HTML, and the query string, which holds the filters, does
	not exist at build time anyway. The shell says the table needs scripts,
	which is what a visitor without them sees.

	The URL is the only store of the filters and the open row, so any view
	can be shared or reloaded. Changes replace the history entry instead of
	adding one: the back button leaves the page rather than stepping back
	through every keystroke.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import {
		getActorsIndex,
		getCampaigns,
		getReports,
		getVulns,
		type ActorsIndex
	} from '$lib/data';
	import {
		NO_FILTERS,
		applyFilters,
		buildIndex,
		parseFilters,
		toRows,
		withFilters,
		withSelection,
		type ExploreRow,
		type Filters
	} from '$lib/search';
	import { formatCount } from '$lib/format';
	import DetailPanel from '$lib/components/DetailPanel.svelte';
	import FilterBar from '$lib/components/FilterBar.svelte';
	import Table from '$lib/components/Table.svelte';

	/** 'static' is the prerendered state, and what a visitor without scripts keeps. */
	let phase = $state<'static' | 'loading' | 'ready' | 'error'>('static');
	let rows = $state.raw<ExploreRow[]>([]);
	let actors = $state.raw<ActorsIndex>([]);
	let kevCves = $state.raw<ReadonlySet<string>>(new Set());

	let heading: HTMLHeadingElement;
	/** The row link that opened the panel, so closing it can return focus there. */
	let opener: HTMLAnchorElement | null = null;

	onMount(async () => {
		phase = 'loading';
		try {
			const [reports, campaigns, vulns, index] = await Promise.all([
				getReports(fetch, 'all'),
				getCampaigns(fetch),
				getVulns(fetch),
				getActorsIndex(fetch)
			]);
			actors = [...index].sort((a, b) => a.name.localeCompare(b.name, 'en'));
			kevCves = new Set(vulns.filter((v) => v.kev_date_added != null).map((v) => v.cve));
			rows = toRows(reports, campaigns, vulns, index);
			phase = 'ready';
		} catch {
			phase = 'error';
		}
	});

	// The query string is read only once the rows are in: before that there
	// is nothing to filter, and during prerender reading it is an error.
	const params = $derived(phase === 'ready' ? page.url.searchParams : new URLSearchParams());
	const filters = $derived<Filters>(phase === 'ready' ? parseFilters(params) : { ...NO_FILTERS });

	// Building the text index takes a moment on a large build, so it waits
	// until the first search and is then kept for as long as the rows are.
	let searchIndex: ReturnType<typeof buildIndex> | null = null;
	let indexedRows: ExploreRow[] | null = null;
	function indexFor(all: ExploreRow[]) {
		if (indexedRows !== all) {
			searchIndex = buildIndex(all);
			indexedRows = all;
		}
		return searchIndex!;
	}

	const shown = $derived(
		applyFilters(rows, filters, filters.q.trim() ? indexFor(rows) : undefined)
	);

	const actorNames = $derived(new Map(actors.map((a) => [a.id, a.name])));
	const sources = $derived(
		[...new Set(rows.flatMap((r) => r.sources))].sort((a, b) => a.localeCompare(b, 'en'))
	);
	// Link-only rows have no publisher by the time they are rows, so ORKL's
	// publishers never reach this list.
	const publishers = $derived(
		[...new Set(rows.map((r) => r.organisation).filter((o): o is string => o != null))].sort(
			(a, b) => a.localeCompare(b, 'en')
		)
	);

	/** What ?report= or ?campaign= asks for. The row is looked up among all rows, not only the shown ones. */
	const requested = $derived.by((): { kind: 'report' | 'campaign'; id: string } | null => {
		const report = params.get('report');
		if (report) return { kind: 'report', id: report };
		const campaign = params.get('campaign');
		if (campaign) return { kind: 'campaign', id: campaign };
		return null;
	});
	const byKey = $derived(new Map(rows.map((r) => [r.key, r])));
	const selected = $derived(requested ? (byKey.get(`${requested.kind}:${requested.id}`) ?? null) : null);

	function navigate(next: URLSearchParams) {
		const url = new URL(page.url);
		url.search = next.toString();
		return goto(url, { replaceState: true, keepFocus: true, noScroll: true });
	}

	function setFilters(next: Filters) {
		navigate(withFilters(page.url.searchParams, next));
	}

	function hrefFor(row: ExploreRow): string {
		const sel = row.kind === 'report' ? { report: row.id } : { campaign: row.id };
		return `?${withSelection(page.url.searchParams, sel)}`;
	}

	function openRow(row: ExploreRow, link: HTMLAnchorElement) {
		opener = link;
		navigate(withSelection(page.url.searchParams, row.kind === 'report' ? { report: row.id } : { campaign: row.id }));
	}

	function closePanel() {
		// Focus moves out of the panel before it closes, or it would fall to
		// the page body. The row link may have scrolled out of the window, in
		// which case the page heading takes it.
		const target = opener?.isConnected ? opener : heading;
		target.focus();
		opener = null;
		navigate(withSelection(page.url.searchParams, {}));
	}
</script>

<svelte:head>
	<title>Explore · APT Explorer</title>
	<meta
		name="description"
		content="Search and filter reports and campaigns by actor, date, source, publisher, CVE and technique."
	/>
</svelte:head>

<div class="intro">
	<h1 tabindex="-1" bind:this={heading}>Explore</h1>
	<p class="lede">
		Reports and campaigns from every source, newest first. The filters are saved in the page
		address, so a filtered view can be bookmarked or shared.
	</p>
</div>

{#if phase === 'error'}
	<p class="notice error" role="alert">
		The report data could not be loaded. Reload the page to try again.
	</p>
{:else}
	<p class="notice" role="status">
		{#if phase === 'static'}
			This table is built in your browser, so it needs scripts to run. Actor pages and the About
			page work without them.
		{:else if phase === 'loading'}
			Loading reports and campaigns…
		{:else}
			Showing <strong>{formatCount(shown.length)}</strong> of {formatCount(rows.length)} reports and
			campaigns{#if !filters.undated && rows.some((r) => r.date == null)}; undated reports are
				hidden{/if}.
		{/if}
	</p>
{/if}

{#if phase === 'ready'}
	<FilterBar {filters} {actors} {sources} {publishers} onchange={setFilters} />
	{#if shown.length}
		<Table
			rows={shown}
			{actorNames}
			selectedKey={selected?.key ?? null}
			actorFilter={filters.actor}
			{hrefFor}
			onopen={openRow}
		/>
	{:else}
		<p class="empty">No report or campaign matches these filters.</p>
	{/if}
	<DetailPanel
		open={requested != null}
		row={selected}
		{requested}
		{actorNames}
		{kevCves}
		onclose={closePanel}
	/>
{/if}

<style>
	.intro {
		max-width: 46rem;
	}

	h1:focus {
		outline: none;
	}

	.lede {
		color: var(--text-muted);
		font-size: 1.0625rem;
	}

	.notice {
		margin: 0 0 1rem;
		color: var(--text-muted);
		font-size: 0.9375rem;
	}

	.notice strong {
		color: var(--text);
		font-family: var(--font-data);
		font-size: 0.875em;
		font-weight: 600;
	}

	.error {
		padding: 0.75rem 1rem;
		border-left: 3px solid var(--danger);
		background: var(--surface);
		color: var(--text);
	}

	.empty {
		padding: 2rem 1rem;
		border: 1px dashed var(--border);
		border-radius: 0.75rem;
		color: var(--text-muted);
		text-align: center;
	}
</style>
