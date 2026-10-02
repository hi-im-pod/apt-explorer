<script lang="ts">
	import { tick } from 'svelte';
	import { base } from '$app/paths';
	import { formatCount, formatDate } from '$lib/format';
	import type { Snapshot } from './$types';
	import { countryName, matchActor, sortActors, type ActorOrder } from './actors';

	let { data } = $props();

	let query = $state('');
	let order = $state<ActorOrder>('recent');
	let box = $state<HTMLElement>();

	// Coming back from a profile restores the search, the sort and how far the
	// list was scrolled, so a reader working through it does not lose their place.
	export const snapshot: Snapshot<{ query: string; order: ActorOrder; top: number }> = {
		capture: () => ({ query, order, top: box?.scrollTop ?? 0 }),
		restore: (value) => {
			query = value.query;
			order = value.order;
			void tick().then(() => {
				if (box) box.scrollTop = value.top;
			});
		}
	};

	const total = $derived(data.actors.length);
	const rows = $derived(
		sortActors(data.actors, order).flatMap((entry) => {
			const m = matchActor(entry, query);
			return m ? [{ entry, via: m.via }] : [];
		})
	);

	// Some actors have dozens of aliases. The row shows the first few, and
	// search still covers every one of them.
	const SHOWN_ALIASES = 6;
	const others = (name: string, aliases: string[]) => aliases.filter((a) => a !== name);
</script>

<svelte:head>
	<title>Actors · APT Explorer</title>
	<meta
		name="description"
		content="Every tracked APT actor, searchable by name, alias or ID, with its origin, report count and latest report."
	/>
</svelte:head>

<div class="intro">
	<h1>Actors</h1>
	<p class="lede">
		{formatCount(total)} actors, merged from the records of MITRE ATT&CK®, the MISP galaxy, ETDA's Threat
		Group Cards and Malpedia. A profile shows which source uses which name.
		<a href="{base}/methodology/">How the records are merged</a>
	</p>
</div>

<form class="controls" role="search" onsubmit={(e) => e.preventDefault()}>
	<div class="field search">
		<label for="actor-search">Search by name, alias or ID</label>
		<input
			id="actor-search"
			type="search"
			bind:value={query}
			placeholder="Fancy Bear, APT28 or G0007"
			autocomplete="off"
			spellcheck="false"
		/>
	</div>
	<div class="field">
		<label for="actor-sort">Sort by</label>
		<select id="actor-sort" bind:value={order}>
			<option value="recent">Most recently reported</option>
			<option value="reports">Most reports</option>
			<option value="name">Name</option>
		</select>
	</div>
</form>

<p class="count" role="status">
	{#if query.trim()}
		Showing {formatCount(rows.length)} of {formatCount(total)} actors.
	{:else}
		Showing all {formatCount(total)} actors.
	{/if}
</p>

{#if rows.length > 0}
	<div class="box" role="region" aria-label="Actors, scrolls" tabindex="0" bind:this={box}>
		<div class="columns" aria-hidden="true">
			<span>Actor</span>
			<span>Origin</span>
			<span>Reports</span>
			<span>Last reported</span>
		</div>
		<ol class="actors" aria-label="Actors">
			{#each rows as { entry, via } (entry.id)}
				{@const aka = others(entry.name, entry.aliases)}
				<li>
					<div class="who">
						<p class="title">
							<a class="name" href="{base}/actors/{entry.id}/">{entry.name}</a>
							<span class="id data">{entry.id}</span>
						</p>
						{#if aka.length > 0}
							<p class="aliases">
								<span class="visually-hidden">Also known as </span>{aka.slice(0, SHOWN_ALIASES).join(', ')}{#if aka.length > SHOWN_ALIASES},
									and {formatCount(aka.length - SHOWN_ALIASES)} more{/if}
							</p>
						{/if}
						{#if via}
							<p class="via">Matches the alias <mark>{via}</mark></p>
						{/if}
					</div>
					<dl class="stats">
						<div class="origin">
							<dt>Origin</dt>
							<dd>
								{#if entry.origin.length > 0}
									{entry.origin.map(countryName).join(', ')}
									{#if entry.origin_conflict}<span class="disagree">sources disagree</span>{/if}
								{:else}
									<span class="muted">not reported</span>
								{/if}
							</dd>
						</div>
						<div>
							<dt>Reports</dt>
							<dd class="data">{formatCount(entry.report_count)}</dd>
						</div>
						<div>
							<dt>Last reported</dt>
							<dd>
								{#if entry.last_reported}
									<time class="data" datetime={entry.last_reported}>{formatDate(entry.last_reported)}</time>
								{:else}
									<span class="muted">none</span>
								{/if}
							</dd>
						</div>
					</dl>
				</li>
			{/each}
		</ol>
	</div>
{:else}
	<p class="empty">
		No actor matches “{query.trim()}”.
	</p>
{/if}

<style>
	.intro {
		max-width: 44rem;
	}

	h1 {
		margin-bottom: 0;
	}

	.lede {
		margin: 1rem 0 0;
		color: var(--text-muted);
		font-size: 1.1875rem;
		line-height: 1.5;
	}

	.controls {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		gap: 0.75rem 1rem;
		margin: 2rem 0 0.75rem;
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		min-width: 0;
	}

	.field.search {
		flex: 1 1 18rem;
		max-width: 32rem;
	}

	label {
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	input,
	select {
		width: 100%;
		min-width: 0;
		height: 2.75rem;
		padding: 0 0.875rem;
		border: 1px solid var(--border);
		border-radius: 0.375rem;
		background: var(--surface);
		color: var(--text);
		font: inherit;
	}

	input::placeholder {
		color: var(--text-muted);
	}

	input:focus-visible,
	select:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 1px;
		border-color: var(--focus);
	}

	.count {
		margin: 0 0 1.25rem;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	/* The list scrolls in its own box so the page stays short. The cap leaves
	   the controls in view, and a row cut off at the bottom shows there is more. */
	.box {
		position: relative;
		max-height: max(20rem, 72dvh);
		overflow-y: auto;
		overscroll-behavior: contain;
		border-bottom: 1px solid var(--border);
	}

	.box:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 2px;
	}

	.box .actors > li:last-child {
		border-bottom: 0;
	}

	/* The ledger: an ink rule under the column names, hairlines between rows. */
	.columns,
	.actors > li {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 0.5rem 1.5rem;
	}

	.columns {
		display: none;
	}

	.actors {
		margin: 0;
		padding: 0;
		list-style: none;
		border-top: 1px solid var(--text);
	}

	.actors > li {
		padding: 0.875rem 0;
		border-bottom: 1px solid var(--border);
	}

	@media (min-width: 52rem) {
		.columns {
			display: grid;
			position: sticky;
			top: 0;
			z-index: 1;
			padding: 0 0 0.5rem;
			border-bottom: 1px solid var(--text);
			background: var(--bg);
			color: var(--text-muted);
			font-family: var(--font-data);
			font-size: 0.6875rem;
		}

		.actors {
			border-top: 0;
		}

		.columns,
		.actors > li {
			grid-template-columns: minmax(0, 1fr) 10rem 5rem 13rem;
			align-items: baseline;
		}

		.columns span:nth-child(3) {
			text-align: right;
		}
	}

	/* A grid or flex child keeps its min-content width unless told not to,
	   and overflow-wrap cannot shrink below it; min-width: 0 lets a long
	   unbroken alias wrap inside the row instead of widening it. */
	.who {
		min-width: 0;
	}

	.title {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.125rem 0.75rem;
		margin: 0;
	}

	.name {
		min-width: 0;
		color: var(--text);
		font-size: 1.125rem;
		font-weight: var(--head-weight);
		font-stretch: var(--head-stretch);
		letter-spacing: -0.01em;
		text-decoration: none;
	}

	.name:hover {
		color: var(--accent);
		text-decoration: underline;
	}

	.id {
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	.aliases,
	.via {
		margin: 0.25rem 0 0;
		color: var(--text-muted);
		font-size: 0.875rem;
		overflow-wrap: anywhere;
	}

	.via mark {
		padding: 0 0.1875rem;
		border-radius: 0.1875rem;
		background: var(--accent-soft);
		color: var(--text);
	}

	.stats {
		display: grid;
		grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.7fr) minmax(0, 1.2fr);
		gap: 0.5rem 1rem;
		margin: 0;
	}

	@media (min-width: 52rem) {
		.stats {
			display: contents;
		}

		.stats dt {
			position: absolute;
			width: 1px;
			height: 1px;
			margin: -1px;
			overflow: hidden;
			clip-path: inset(50%);
			white-space: nowrap;
		}

		.stats dd.data {
			text-align: right;
		}
	}

	.stats div {
		min-width: 0;
	}

	dt {
		margin: 0 0 0.125rem;
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	dd {
		margin: 0;
		font-size: 0.875rem;
	}

	dd.data,
	dd .data {
		font-size: 0.8125rem;
	}

	.muted {
		color: var(--text-muted);
	}

	.disagree {
		display: block;
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	.empty {
		padding: 1.25rem 0;
		border-top: 1px solid var(--text);
		border-bottom: 1px solid var(--border);
		color: var(--text-muted);
	}
</style>
