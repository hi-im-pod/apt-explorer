<script lang="ts">
	import { base } from '$app/paths';
	import { formatCount, formatDate } from '$lib/format';
	import type { Snapshot } from './$types';
	import { countryName, matchActor, sortActors, type ActorOrder } from './actors';

	let { data } = $props();

	let query = $state('');
	let order = $state<ActorOrder>('recent');

	// Coming back from a profile restores the search and sort, so a reader
	// working through a filtered list does not have to type it again.
	export const snapshot: Snapshot<{ query: string; order: ActorOrder }> = {
		capture: () => ({ query, order }),
		restore: (value) => {
			query = value.query;
			order = value.order;
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
		{formatCount(total)} actors, each merged from the records of MITRE ATT&CK®, the MISP galaxy, ETDA's
		Threat Group Cards and Malpedia. A profile lists every alias with the source that gives it, and
		the reports linked to the actor.
	</p>
	<p class="note"><a href="{base}/methodology/">How the records are merged</a></p>
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
					<div>
						<dt>Origin</dt>
						<dd>
							{#if entry.origin.length > 0}
								{entry.origin.map(countryName).join(', ')}
								{#if entry.origin.length > 1}<span class="disagree">sources disagree</span>{/if}
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
{:else}
	<p class="empty">
		No actor matches “{query.trim()}”. Try another spelling or another of the actor's names.
	</p>
{/if}

<style>
	.intro {
		max-width: 44rem;
	}

	.lede {
		font-size: 1.125rem;
	}

	.note {
		font-size: 0.9375rem;
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
		font-size: 0.875rem;
		font-weight: 550;
	}

	input,
	select {
		width: 100%;
		min-width: 0;
		padding: 0.5rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 0.5rem;
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
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.actors {
		display: grid;
		gap: 0.625rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.actors > li {
		display: grid;
		gap: 0.75rem 2rem;
		padding: 1rem 1.125rem;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 0.75rem;
	}

	@media (min-width: 52rem) {
		.actors > li {
			grid-template-columns: minmax(0, 1fr) auto;
			align-items: start;
		}
	}

	/* A grid or flex child keeps its min-content width unless told not to,
	   and overflow-wrap cannot shrink below it; min-width: 0 lets a long
	   unbroken alias wrap inside the card instead of widening it. */
	.who {
		min-width: 0;
	}

	.title {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.125rem 0.625rem;
		margin: 0;
	}

	.name {
		min-width: 0;
		font-size: 1.0625rem;
		font-weight: 650;
		text-decoration: none;
	}

	.name:hover {
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
			grid-template-columns: 9.5rem 4.5rem 10.5rem;
		}
	}

	.stats div {
		min-width: 0;
	}

	dt {
		margin: 0 0 0.125rem;
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
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
		padding: 1.25rem;
		border: 1px dashed var(--border);
		border-radius: 0.75rem;
		color: var(--text-muted);
	}
</style>
