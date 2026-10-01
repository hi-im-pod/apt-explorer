<!--
	Explore: every report and campaign in one filterable table.

	The page is prerendered as a shell, and the rows load in the browser.
	Loading them in a prerendered load function would inline the whole
	report index into the HTML, and the query string, which holds the
	filters, does not exist at build time anyway. The shell says the table
	needs scripts, which is what a visitor without them sees.

	The rows come from one compact index (about 1 MB compressed), not from
	the report shards, which are 19 MB. A report's own record is read from
	its one year shard when its panel opens. The data layer keeps both under
	URLs that carry the build time, so a browser or the service worker can
	keep them for as long as the build lasts.

	The URL is the only store of the filters and the open row, so any view
	can be shared or reloaded. Changes replace the history entry instead of
	adding one: the back button leaves the page rather than stepping back
	through every keystroke.
-->
<script lang="ts">
	import { onMount, tick, untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import {
		getExploreData,
		getReportDetail,
		type ActorsIndex,
		type Build,
		type Report
	} from '$lib/data';
	import {
		NO_FILTERS,
		applyFilters,
		facets,
		kevCves as kevCvesOf,
		parseFilters,
		rowLookup,
		toRows,
		withFilters,
		withSelection,
		type ExploreRow,
		type Filters
	} from '$lib/search';
	import { formatCount } from '$lib/format';
	import { clampPage, pageCount, pageOfIndex, parsePaging, withPaging } from '$lib/paging';
	import DetailPanel from '$lib/components/DetailPanel.svelte';
	import FilterBar from '$lib/components/FilterBar.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import Table from '$lib/components/Table.svelte';

	/** After this long the loading note admits it is slow, so a slow line does not look like a stuck page. */
	const SLOW_AFTER_MS = 4000;

	/** 'static' is the prerendered state, and what a visitor without scripts keeps. */
	let phase = $state<'static' | 'loading' | 'ready' | 'error'>('static');
	let slow = $state(false);
	let offline = $state(false);
	let rows = $state.raw<ExploreRow[]>([]);
	let actors = $state.raw<ActorsIndex>([]);
	let kevCves = $state.raw<ReadonlySet<string>>(new Set());
	let build: Build | null = null;
	let idLen = 8;
	let find: ReturnType<typeof rowLookup> = () => null;

	let heading: HTMLHeadingElement;
	let tableHeading = $state<HTMLHeadingElement>();
	/** The row link that opened the panel, so closing it can return focus there. */
	let opener: HTMLAnchorElement | null = null;

	/**
	 * Read the index, the campaigns and the actor names. The page shows no
	 * report text of its own until this is done, and the whole download is
	 * about a megabyte, so a slow line gets a note rather than a blank page.
	 */
	async function load() {
		phase = 'loading';
		slow = false;
		const timer = setTimeout(() => (slow = true), SLOW_AFTER_MS);
		try {
			const data = await getExploreData(fetch);
			build = data.build;
			idLen = data.index.id_len;
			actors = [...data.actors].sort((a, b) => a.name.localeCompare(b.name, 'en'));
			kevCves = kevCvesOf(data.index);
			rows = toRows(data.index, data.campaigns, data.actors);
			find = rowLookup(rows, idLen);
			phase = 'ready';
		} catch {
			offline = typeof navigator !== 'undefined' && navigator.onLine === false;
			phase = 'error';
		} finally {
			clearTimeout(timer);
		}
	}

	onMount(load);

	/**
	 * The retry button is removed once the list loads, which would drop keyboard focus to the top
	 * of the document. The page heading takes it instead.
	 */
	async function retry() {
		await load();
		if (phase !== 'ready') return;
		await tick();
		heading.focus();
	}

	// The query string is read only once the rows are in: before that there
	// is nothing to filter, and during prerender reading it is an error.
	const params = $derived(phase === 'ready' ? page.url.searchParams : new URLSearchParams());
	const filters = $derived<Filters>(phase === 'ready' ? parseFilters(params) : { ...NO_FILTERS });

	const shown = $derived(applyFilters(rows, filters));

	const actorNames = $derived(new Map(actors.map((a) => [a.id, a.name])));
	const facet = $derived(facets(rows));
	const sources = $derived(facet.sources);
	// Link-only rows have no publisher by the time they are rows, so ORKL's
	// publishers never reach this list.
	const publishers = $derived(facet.publishers);

	/** What ?report= or ?campaign= asks for. The row is looked up among all rows, not only the shown ones. */
	const requested = $derived.by((): { kind: 'report' | 'campaign'; id: string } | null => {
		const report = params.get('report');
		if (report) return { kind: 'report', id: report };
		const campaign = params.get('campaign');
		if (campaign) return { kind: 'campaign', id: campaign };
		return null;
	});
	const selected = $derived(requested ? find(requested.kind, requested.id) : null);

	/**
	 * The page comes from the address. With no page in it, an open report or campaign
	 * decides: the table opens on the page that holds it. A page past the end is
	 * clamped to the last one rather than shown empty.
	 */
	const size = $derived(parsePaging(params).size);
	const wantedPage = $derived.by(() => {
		if (params.has('page')) return parsePaging(params).page;
		if (!selected) return 1;
		const at = shown.findIndex((r) => r.key === selected.key);
		return at < 0 ? 1 : pageOfIndex(at, size);
	});
	const pageNumber = $derived(clampPage(wantedPage, shown.length, size));
	const pages = $derived(pageCount(shown.length, size));
	const offset = $derived((pageNumber - 1) * size);
	const pageRows = $derived(shown.slice(offset, offset + size));

	// An out-of-range page in the address is corrected in place, so the address
	// always says what the table shows.
	$effect(() => {
		if (phase === 'ready' && params.has('page') && wantedPage !== pageNumber) {
			navigate(withPaging(page.url.searchParams, { page: pageNumber, size }));
		}
	});

	/**
	 * The open report's full record, read from its year shard. The panel shows
	 * the row's own fields at once and waits on this only for the links.
	 */
	let detail = $state.raw<{ key: string; status: 'loading' | 'error' | 'ready'; report: Report | null } | null>(
		null
	);

	function loadDetail(row: ExploreRow) {
		if (!build) return;
		const key = row.key;
		detail = { key, status: 'loading', report: null };
		getReportDetail(fetch, build, idLen, { id: row.id, published: row.date })
			.then((report) => {
				// A visitor may have opened another row while this one loaded.
				if (detail?.key === key) detail = { key, status: 'ready', report };
			})
			.catch(() => {
				if (detail?.key === key) detail = { key, status: 'error', report: null };
			});
	}

	$effect(() => {
		const row = selected;
		untrack(() => {
			if (row?.kind === 'report') loadDetail(row);
			else detail = null;
		});
	});

	const panelDetail = $derived(detail && detail.key === selected?.key ? detail : null);

	function navigate(next: URLSearchParams) {
		const url = new URL(page.url);
		url.search = next.toString();
		return goto(url, { replaceState: true, keepFocus: true, noScroll: true });
	}

	/** Move to a page. With a row open, page 1 is written out, or the row's own page would win. */
	async function goToPage(n: number) {
		const next = withPaging(page.url.searchParams, { page: n, size });
		if (n === 1 && (next.has('report') || next.has('campaign'))) next.set('page', '1');
		await navigate(next);
		await tick();
		tableHeading?.focus();
	}

	async function setSize(n: number) {
		await navigate(withPaging(page.url.searchParams, { page: 1, size: n }));
		await tick();
		tableHeading?.focus();
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
	<p class="lede">Reports and campaigns from every source, newest first.</p>
</div>

{#if phase === 'error'}
	<p class="notice error" role="alert">
		{#if offline}
			You are offline, and this browser has no saved copy of the report list. Connect to the
			internet, then try again.
		{:else}
			The report list could not be loaded. Check your connection, then try again.
		{/if}
		<button type="button" class="retry" onclick={retry}>Try again</button>
	</p>
{:else}
	<p class="notice" role="status">
		{#if phase === 'static'}
			This table is built in your browser, so it needs scripts to run. Actor pages and the About
			page work without them.
		{:else if phase === 'loading'}
			Loading reports and campaigns…
			{#if slow}
				This is taking a while. Later visits reuse the saved copy.
			{/if}
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
		<section class="region" aria-labelledby="table-heading">
			<h2 id="table-heading" tabindex="-1" bind:this={tableHeading}>Reports and campaigns</h2>
			<div class="frame">
			<Pagination
				position="top"
				page={pageNumber}
				count={pages}
				{size}
				total={shown.length}
				onpage={goToPage}
				onsize={setSize}
			/>
			<Table
				rows={pageRows}
				{offset}
				total={shown.length}
				{actorNames}
				selectedKey={selected?.key ?? null}
				actorFilter={filters.actor}
				{hrefFor}
				onopen={openRow}
			/>
			<Pagination
				position="bottom"
				page={pageNumber}
				count={pages}
				{size}
				total={shown.length}
				onpage={goToPage}
				onsize={setSize}
			/>
			</div>
		</section>
	{:else}
		<p class="empty">No report or campaign matches these filters.</p>
	{/if}
	<DetailPanel
		open={requested != null}
		row={selected}
		{requested}
		{actorNames}
		{kevCves}
		report={panelDetail?.report ?? null}
		status={panelDetail?.status ?? 'loading'}
		onretry={() => selected && loadDetail(selected)}
		onclose={closePanel}
	/>
{/if}

<style>
	.intro {
		max-width: 46rem;
		margin-bottom: 1.5rem;
	}

	h1:focus {
		outline: none;
	}

	.lede {
		margin: 0;
		color: var(--text-muted);
		font-size: 1.125rem;
	}

	.notice {
		margin: 0 0 0.75rem;
		color: var(--text-muted);
		font-size: 0.875rem;
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

	.retry {
		margin-left: 0.5rem;
		padding: 0.25rem 0.875rem;
		background: transparent;
		border: 1px solid var(--border);
		border-radius: 0.375rem;
		color: var(--text);
		font: inherit;
		font-size: 0.875rem;
		cursor: pointer;
	}

	.retry:hover {
		border-color: var(--accent);
	}

	.region {
		margin-top: 1.5rem;
	}

	.region h2 {
		margin: 0 0 0.75rem;
		font-size: 1.125rem;
	}

	.region h2:focus {
		outline: none;
	}

	/* The bordered region: range and pager above the rows, page size below. */
	.frame {
		overflow: hidden;
		border: 1px solid var(--border);
		border-radius: 0.5rem;
		background: var(--surface);
	}

	.empty {
		padding: 2rem 1rem;
		border: 1px dashed var(--border);
		border-radius: 0.5rem;
		color: var(--text-muted);
		text-align: center;
	}
</style>
