<script lang="ts">
	import { base } from '$app/paths';
	import { sourceLabel } from '$lib/data/labels';
	import { formatCount, formatDate, lastSpan } from '$lib/format';
	import { aliasGrid, numberWord, publishShort } from '$lib/home';

	let { data } = $props();

	const grid = $derived(
		aliasGrid(
			data.actor,
			data.sources.map((s) => s.name)
		)
	);
	const hidden = $derived(grid.total - grid.rows.length);

	const ways = $derived([
		{
			path: '/explore/',
			title: 'Explore reports',
			text: 'Every report and campaign in one table you can filter by actor, source, date or CVE.',
			count: data.build ? `${formatCount(data.build.report_count)} reports` : null
		},
		{
			path: '/actors/',
			title: 'Actors',
			text: 'One page per group: names, malware, techniques, CVEs, and the reports behind them.',
			count: `${formatCount(data.actorCount)} actors`
		},
		{
			path: '/trends/',
			title: 'Trends',
			text: `Which groups and techniques show up in ${lastSpan(data.build?.recent_months)} of reporting.`,
			count: data.build ? `Since ${formatDate(data.build.recent_since)}` : null
		},
		{
			path: '/guesses/',
			title: 'Name guesses',
			text: "Names from the paper's reports that match no known group. A program labels each one and gives a score and the evidence.",
			count: `${formatCount(data.guessCount)} guesses`
		},
		{
			path: '/about/#sources',
			title: 'Sources',
			text: 'Where every fact comes from, what we may publish from it, and when it was last fetched.',
			count: `${formatCount(data.sources.length)} sources`
		}
	]);
</script>

<svelte:head>
	<title>APT Explorer</title>
	<meta
		name="description"
		content="Advanced persistent threat actors, their aliases and the reports written about them, merged from open sources and rebuilt every week."
	/>
</svelte:head>

<section class="hero" aria-labelledby="hero-heading">
	<div class="hero-copy">
		<h1 id="hero-heading">One group, <span class="nw">{numberWord(grid.total)}</span> names.</h1>
		<p class="lede">
			Vendors each name the same threat actor differently. APT Explorer lines up {numberWord(
				grid.columns.length
			)} public datasets, shows which source uses which name, and links every fact to the report it came
			from.
		</p>
		<form class="find" role="search" action="{base}/explore/" method="get">
			<input
				type="search"
				name="q"
				autocomplete="off"
				placeholder="Search a group, alias or CVE"
				aria-label="Search reports by group, alias or CVE"
			/>
			<button class="btn" type="submit">Search</button>
		</form>
	</div>

	<div class="hero-grid">
		<p class="grid-caption" id="grid-caption">
			{data.actor.name}, as {numberWord(grid.columns.length)} sources name it. A filled square means
			that source lists the name. The rows sample the {grid.total} names, from the most widely listed
			to the least.
		</p>
		<div class="alias-card">
			<table class="alias-grid" aria-labelledby="grid-caption">
				<colgroup>
					<col />
					{#each grid.columns as key (key)}
						<col class="src" />
					{/each}
				</colgroup>
				<thead>
					<tr>
						<th scope="col">Name used in reports</th>
						{#each grid.columns as key (key)}
							<th scope="col" class="src">{sourceLabel(key).short}</th>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each grid.rows as row, i (row.name)}
						<tr class:picked={row.primary} style:--i={i}>
							<th scope="row" class="name">{row.name}</th>
							{#each grid.columns as key (key)}
								{@const listed = row.sources.includes(key)}
								<td class="src">
									<span class="m" class:no={!listed} aria-hidden="true"></span>
									<span class="visually-hidden">{listed ? 'Lists this name' : 'Does not list this name'}</span>
								</td>
							{/each}
						</tr>
					{/each}
				</tbody>
			</table>
			{#if hidden > 0}
				<p class="more">and {hidden} more names for this group</p>
			{/if}
		</div>
	</div>
</section>

<section class="ways" aria-labelledby="ways-heading">
	<h2 id="ways-heading">Ways in</h2>
	<ul class="ledger">
		{#each ways as way (way.path)}
			<li>
				<a href="{base}{way.path}">{way.title}</a>
				<p>{way.text}</p>
				{#if way.count}<span class="n">{way.count}</span>{/if}
			</li>
		{/each}
	</ul>
</section>

<section class="sources" aria-labelledby="sources-heading">
	<h2 id="sources-heading">Where the data comes from</h2>
	<table class="tbl">
		<thead>
			<tr>
				<th scope="col">Source</th>
				<th scope="col" class="hide-sm">What we use</th>
				<th scope="col">What we publish</th>
				<th scope="col" class="hide-sm">Terms</th>
			</tr>
		</thead>
		<tbody>
			{#each data.sources as s (s.name)}
				{@const label = sourceLabel(s.name)}
				<tr class:stale={s.stale}>
					<th scope="row">
						{label.name}
						<span class="fetch">
							<span class="status">{s.stale ? 'Stale' : 'Current'}</span>
							{#if s.last_success}<time datetime={s.last_success}>{formatDate(s.last_success)}</time
								>{:else}never fetched{/if}, <span class="data">{formatCount(s.record_count)}</span> records
						</span>
					</th>
					<td class="hide-sm muted">{label.role}</td>
					<td><span class="pill">{publishShort(s.publish)}</span></td>
					<td class="hide-sm"><a href={s.licence_url}>{s.licence}</a></td>
				</tr>
			{/each}
		</tbody>
	</table>
	<p class="key">
		Each source is fetched every week. When a fetch fails, the build keeps the last good snapshot and
		marks the source stale. <a href="{base}/about/#sources">Full licence table and fetch dates</a>
	</p>
	<p class="credit">
		Built on the dataset of Yuldoshkhujaev et al. (CCS '25). <a href="{base}/about/#paper-heading"
			>About has the full credit</a
		>.
	</p>
</section>

<style>
	/* ---- hero ---- */
	.hero {
		display: grid;
		gap: 2rem;
		padding-bottom: 2.5rem;
		border-bottom: 1px solid var(--border);
	}

	.hero h1 {
		margin: 0;
	}

	.nw {
		white-space: nowrap;
	}

	.lede {
		max-width: 38rem;
		margin: 1rem 0 0;
		color: var(--text-muted);
		font-size: 1.1875rem;
		line-height: 1.5;
	}

	@media (min-width: 45rem) {
		.hero {
			grid-template-columns: minmax(0, 5fr) minmax(0, 7fr);
			gap: 3rem;
			align-items: start;
		}
	}

	.find {
		display: flex;
		gap: 0.5rem;
		max-width: 30rem;
		margin-top: 1.75rem;
	}

	.find input {
		flex: 1;
		min-width: 0;
		height: 2.75rem;
		padding: 0 0.875rem;
		font: inherit;
		color: var(--text);
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 0.375rem;
	}

	@media (max-width: 44.99rem) {
		.find input {
			padding: 0 0.5rem;
			font-size: 0.9375rem;
		}

		.find {
			gap: 0.375rem;
		}

		.find .btn {
			padding: 0 0.75rem;
			font-size: 0.9375rem;
		}
	}

	.find input::placeholder {
		color: var(--text-muted);
		opacity: 1;
		font-size: 0.8125rem;
	}

	@media (max-width: 44.99rem) {
		.find input::placeholder {
			font-size: 0.6875rem;
		}
	}

	.find input:hover {
		border-color: var(--text-muted);
	}

	.btn {
		height: 2.75rem;
		padding: 0 1.125rem;
		font: inherit;
		font-weight: 650;
		color: var(--ink-on-accent);
		background: var(--accent);
		border: 0;
		border-radius: 0.375rem;
		cursor: pointer;
	}

	.btn:hover {
		filter: brightness(0.92);
	}

	/* ---- alias by source grid ---- */
	.grid-caption {
		max-width: 34rem;
		margin: 0 0 0.75rem;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.alias-card {
		padding: 0.25rem 0;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 0.5rem;
	}

	.alias-grid {
		width: 100%;
		border-collapse: collapse;
		table-layout: fixed;
	}

	.alias-grid col.src {
		width: 4.5rem;
	}

	.alias-grid th,
	.alias-grid td {
		padding: 0;
		font-weight: 400;
		text-align: left;
		border-bottom: 1px solid var(--grid);
	}

	.alias-grid thead th {
		height: 2.5rem;
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		font-weight: 500;
		border-bottom-color: var(--border);
	}

	.alias-grid tbody tr:last-child > * {
		border-bottom: 0;
	}

	.alias-grid th:first-child {
		padding-left: 1rem;
	}

	.alias-grid th.src,
	.alias-grid td.src {
		text-align: center;
	}

	.alias-grid th.name {
		height: 2.125rem;
		color: var(--text);
		font-size: 0.9375rem;
	}

	.alias-grid tr.picked {
		background: var(--accent-soft);
	}

	.alias-grid tr.picked th.name {
		font-weight: 650;
	}

	.m {
		display: inline-block;
		width: 0.75rem;
		height: 0.75rem;
		vertical-align: middle;
		background: var(--text);
		border-radius: 2px;
	}

	.m.no {
		background: none;
		box-shadow: inset 0 0 0 1px var(--text-muted);
	}

	.more {
		margin: 0;
		padding: 0.5rem 1rem;
		color: var(--text-muted);
		font-size: 0.8125rem;
		border-top: 1px solid var(--grid);
	}

	@media (max-width: 44.99rem) {
		.alias-grid col.src {
			width: 3.5rem;
		}

		.alias-grid th:first-child {
			padding-left: 0.5rem;
		}

		.alias-grid thead th {
			font-size: 0.5625rem;
			overflow-wrap: normal;
			white-space: nowrap;
		}

		.alias-grid thead th:first-child {
			padding-right: 0.25rem;
			line-height: 1.2;
			white-space: normal;
		}

		.alias-grid th.name {
			font-size: 0.875rem;
		}

		.more {
			padding-inline: 0.5rem;
		}
	}

	/* The page's one load animation: the grid's rows come in one after another. */
	@media (prefers-reduced-motion: no-preference) {
		.alias-grid tbody tr {
			animation: row-in 0.35s ease-out backwards;
			animation-delay: calc(var(--i) * 40ms);
		}

		@keyframes row-in {
			from {
				opacity: 0;
				transform: translateY(4px);
			}
		}
	}

	/* ---- ways in ---- */
	.ways h2,
	.sources h2 {
		margin-top: 2.5rem;
	}

	.ledger {
		margin: 0;
		padding: 0;
		list-style: none;
		border-top: 1px solid var(--text);
	}

	.ledger li {
		position: relative;
		display: grid;
		gap: 0.25rem;
		align-items: baseline;
		padding: 1rem 0;
		border-bottom: 1px solid var(--border);
	}

	@media (min-width: 45rem) {
		.ledger li {
			grid-template-columns: 13rem minmax(0, 1fr) 9rem;
			gap: 1.5rem;
		}

		.ledger .n {
			text-align: right;
		}
	}

	.ledger a {
		color: var(--text);
		font-size: 1.125rem;
		font-weight: var(--head-weight);
		font-stretch: var(--head-stretch);
		text-decoration: none;
	}

	/* The whole row is the target, so a finger does not have to find the name. */
	.ledger a::after {
		content: '';
		position: absolute;
		inset: 0;
	}

	.ledger li:hover a {
		color: var(--accent);
	}

	.ledger a:focus-visible {
		outline: none;
	}

	.ledger a:focus-visible::after {
		outline: 2px solid var(--focus);
		outline-offset: 2px;
		border-radius: 2px;
	}

	.ledger p {
		margin: 0;
		color: var(--text-muted);
	}

	.ledger .n {
		font-family: var(--font-data);
		font-size: 0.8125rem;
		font-weight: 500;
	}

	/* ---- where the data comes from ---- */
	.tbl {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.9375rem;
	}

	.tbl thead th {
		padding: 0.5rem 0.75rem 0.5rem 0;
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		font-weight: 500;
		text-align: left;
		border-bottom: 1px solid var(--text);
	}

	.tbl td,
	.tbl tbody th {
		padding: 0.625rem 0.75rem 0.625rem 0;
		font-weight: 400;
		text-align: left;
		vertical-align: baseline;
		border-bottom: 1px solid var(--border);
	}

	.tbl tbody th {
		font-weight: 550;
	}

	.fetch {
		display: block;
		color: var(--text-muted);
		font-size: 0.8125rem;
		font-weight: 400;
	}

	.fetch .data {
		font-family: var(--font-data);
		font-size: 0.75rem;
	}

	.status {
		font-weight: 600;
	}

	.stale .status {
		color: var(--danger);
	}

	.pill {
		display: inline-block;
		padding: 0.0625rem 0.5rem;
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		font-weight: 500;
		white-space: nowrap;
		border: 1px solid var(--border);
		border-radius: 99px;
	}

	.key,
	.credit {
		max-width: 42rem;
		margin: 0.75rem 0 0;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	@media (max-width: 44.99rem) {
		.tbl .hide-sm {
			display: none;
		}
	}
</style>
