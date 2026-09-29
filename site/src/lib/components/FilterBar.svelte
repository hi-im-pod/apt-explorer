<!--
	The explore filters. The URL holds their state; this component only shows
	it and reports changes.

	Selects, dates and switches report a change at once. Text fields keep a
	draft while the visitor types and report it after a short pause, so each
	keystroke does not become a navigation. The draft is replaced from the
	URL only when the URL changes to something this component did not send,
	such as "Clear filters", so a slow navigation can never overwrite what is
	being typed.
-->
<script lang="ts">
	import type { ActorsIndex } from '$lib/data/types';
	import { NO_FILTERS, type Filters } from '$lib/search';
	import { sourceLabel } from '$lib/data/labels';

	interface Props {
		filters: Filters;
		actors: ActorsIndex;
		/** Source keys that have at least one row. */
		sources: string[];
		/** Publishers that may be shown, which leaves out link-only rows. */
		publishers: string[];
		onchange: (next: Filters) => void;
	}

	let { filters, actors, sources, publishers, onchange }: Props = $props();

	const TEXT_DELAY_MS = 250;
	type TextKey = 'q' | 'cve' | 'tech';

	// The last value of each text field that came from, or went to, the URL.
	const synced: Record<TextKey, string> = { q: '', cve: '', tech: '' };
	let drafts = $state<Record<TextKey, string>>({ q: '', cve: '', tech: '' });
	const timers: Partial<Record<TextKey, ReturnType<typeof setTimeout>>> = {};

	$effect(() => {
		for (const key of ['q', 'cve', 'tech'] as const) {
			const fromUrl = filters[key] ?? '';
			if (fromUrl !== synced[key]) {
				synced[key] = fromUrl;
				drafts[key] = fromUrl;
			}
		}
	});

	function send(key: TextKey) {
		clearTimeout(timers[key]);
		const value = drafts[key].trim();
		if (value === synced[key]) return;
		synced[key] = value;
		onchange({ ...filters, [key]: key === 'q' ? value : value || null });
	}

	function typed(key: TextKey, value: string) {
		drafts[key] = value;
		clearTimeout(timers[key]);
		timers[key] = setTimeout(() => send(key), TEXT_DELAY_MS);
	}

	function clear() {
		// A draft still waiting to be sent would otherwise re-apply itself.
		for (const key of ['q', 'cve', 'tech'] as const) clearTimeout(timers[key]);
		onchange({ ...NO_FILTERS });
	}

	function set<K extends keyof Filters>(key: K, value: Filters[K]) {
		onchange({ ...filters, [key]: value });
	}

	/** Filters other than the text search, which stays visible on every screen. */
	const others = $derived(
		[
			filters.from,
			filters.to,
			filters.actor,
			filters.source,
			filters.org,
			filters.cve,
			filters.tech,
			filters.kev,
			filters.undated
		].filter(Boolean).length
	);
	const active = $derived(others > 0 || Boolean(filters.q));

	// On a narrow screen the other filters fold away, so the rows start on
	// the first screen. Wide screens show them all and ignore this.
	let expanded = $state(false);

	// A value in the URL that is not among the options still shows as chosen.
	const actorKnown = $derived(!filters.actor || actors.some((a) => a.id === filters.actor));
	const sourceKnown = $derived(!filters.source || sources.includes(filters.source));
	const publisherKnown = $derived(!filters.org || publishers.includes(filters.org));
</script>

<form class="filters" role="search" aria-label="Filter reports and campaigns" onsubmit={(e) => e.preventDefault()}>
	<div class="field search">
		<label for="f-q">Search</label>
		<input
			id="f-q"
			type="search"
			autocomplete="off"
			placeholder="Title, publisher, actor, CVE or technique"
			value={drafts.q}
			oninput={(e) => typed('q', e.currentTarget.value)}
			onchange={() => send('q')}
		/>
	</div>

	<button
		type="button"
		class="more"
		aria-expanded={expanded}
		aria-controls="filter-fields"
		onclick={() => (expanded = !expanded)}
	>
		{expanded ? 'Fewer filters' : 'More filters'}{#if others}<span class="count"> · {others} on</span>{/if}
	</button>

	<div id="filter-fields" class="rest" class:expanded>
		<div class="field">
			<label for="f-actor">Actor</label>
			<select id="f-actor" value={filters.actor ?? ''} onchange={(e) => set('actor', e.currentTarget.value || null)}>
				<option value="">Any actor</option>
				{#if !actorKnown}<option value={filters.actor}>{filters.actor}</option>{/if}
				{#each actors as a (a.id)}<option value={a.id}>{a.name}</option>{/each}
			</select>
		</div>

		<div class="field">
			<label for="f-source">Source</label>
			<select id="f-source" value={filters.source ?? ''} onchange={(e) => set('source', e.currentTarget.value || null)}>
				<option value="">Any source</option>
				{#if !sourceKnown}<option value={filters.source}>{filters.source}</option>{/if}
				{#each sources as s (s)}<option value={s}>{sourceLabel(s).name}</option>{/each}
			</select>
		</div>

		<div class="field">
			<label for="f-org">Publisher</label>
			<select id="f-org" value={filters.org ?? ''} onchange={(e) => set('org', e.currentTarget.value || null)}>
				<option value="">Any publisher</option>
				{#if !publisherKnown}<option value={filters.org}>{filters.org}</option>{/if}
				{#each publishers as p (p)}<option value={p}>{p}</option>{/each}
			</select>
		</div>

		<div class="field">
			<label for="f-from">From</label>
			<input
				id="f-from"
				type="date"
				value={filters.from ?? ''}
				onchange={(e) => set('from', e.currentTarget.value || null)}
			/>
		</div>

		<div class="field">
			<label for="f-to">To</label>
			<input
				id="f-to"
				type="date"
				value={filters.to ?? ''}
				onchange={(e) => set('to', e.currentTarget.value || null)}
			/>
		</div>

		<div class="field">
			<label for="f-cve">CVE</label>
			<input
				id="f-cve"
				class="data"
				type="text"
				autocomplete="off"
				spellcheck="false"
				placeholder="CVE-2024-3400"
				value={drafts.cve}
				oninput={(e) => typed('cve', e.currentTarget.value)}
				onchange={() => send('cve')}
			/>
		</div>

		<div class="field">
			<label for="f-tech">Technique</label>
			<input
				id="f-tech"
				class="data"
				type="text"
				autocomplete="off"
				spellcheck="false"
				placeholder="T1566"
				value={drafts.tech}
				oninput={(e) => typed('tech', e.currentTarget.value)}
				onchange={() => send('tech')}
			/>
		</div>

		<div class="switches">
			<label class="switch">
				<input type="checkbox" checked={filters.kev} onchange={(e) => set('kev', e.currentTarget.checked)} />
				Only CVEs in CISA KEV
			</label>
			<label class="switch">
				<input
					type="checkbox"
					checked={filters.undated}
					onchange={(e) => set('undated', e.currentTarget.checked)}
				/>
				Include undated reports
			</label>
			<button
				type="button"
				class="clear"
				disabled={!active}
				onclick={clear}>Clear filters</button
			>
		</div>
	</div>
</form>

<style>
	.filters {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.75rem;
		margin: 0 0 1.25rem;
		padding: 1rem;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 0.75rem;
	}

	@media (min-width: 45rem) {
		.filters {
			grid-template-columns: repeat(4, minmax(0, 1fr));
			gap: 0.875rem 1rem;
			padding: 1.125rem 1.25rem;
		}
	}

	.field {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		min-width: 0;
	}

	.search {
		grid-column: 1 / -1;
	}

	/* Narrow screens: the fields after the search fold behind a toggle. */
	.rest {
		display: none;
		grid-column: 1 / -1;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.75rem;
	}

	.rest.expanded {
		display: grid;
	}

	.more {
		grid-column: 1 / -1;
		justify-self: start;
		padding: 0.375rem 0.875rem;
		background: transparent;
		color: var(--text);
		border: 1px solid var(--border);
		border-radius: 999px;
		font: inherit;
		font-size: 0.875rem;
		font-weight: 550;
		cursor: pointer;
	}

	.more:hover {
		border-color: var(--accent);
	}

	.count {
		color: var(--accent);
	}

	@media (min-width: 45rem) {
		/* Wide screens: every field sits in the form's own grid. */
		.rest,
		.rest.expanded {
			display: contents;
		}

		.more {
			display: none;
		}
	}

	label {
		color: var(--text-muted);
		font-size: 0.8125rem;
		font-weight: 550;
	}

	input[type='search'],
	input[type='text'],
	input[type='date'],
	select {
		width: 100%;
		min-width: 0;
		min-height: 2.5rem;
		padding: 0.4375rem 0.625rem;
		background: var(--bg);
		color: var(--text);
		border: 1px solid var(--border);
		border-radius: 0.5rem;
		font: inherit;
		font-size: 0.9375rem;
	}

	input.data {
		font-family: var(--font-data);
		font-size: 0.8125rem;
	}

	input::placeholder {
		color: var(--text-muted);
		opacity: 1;
	}

	input:hover,
	select:hover {
		border-color: var(--text-muted);
	}

	input:focus-visible,
	select:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 0;
		border-color: var(--focus);
	}

	.switches {
		grid-column: 1 / -1;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 1.5rem;
	}

	.switch {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		color: var(--text);
		font-size: 0.9375rem;
		font-weight: 450;
		cursor: pointer;
	}

	.switch input {
		width: 1.125rem;
		height: 1.125rem;
		margin: 0;
		accent-color: var(--accent);
	}

	.clear {
		margin-left: auto;
		padding: 0.375rem 0.875rem;
		background: transparent;
		color: var(--accent);
		border: 1px solid var(--accent);
		border-radius: 999px;
		font: inherit;
		font-size: 0.875rem;
		font-weight: 550;
		cursor: pointer;
	}

	.clear:disabled {
		color: var(--text-muted);
		border-color: var(--border);
		cursor: default;
	}

	@media (max-width: 30rem) {
		.clear {
			margin-left: 0;
		}
	}
</style>
