<script lang="ts">
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { formatCount } from '$lib/format';
	import type { GuessBand, GuessLabel } from '$lib/data/types';
	import {
		BANDS,
		LABELS,
		bandText,
		confidenceText,
		countBy,
		filterGuesses,
		gainText,
		kindText,
		labelText,
		percentText,
		weightText
	} from './view';

	let { data } = $props();

	const evaluation = $derived(data.guesses.evaluation);
	const rows = $derived(data.guesses.guesses);

	// The filters change what is listed, so they need scripts. They appear
	// only after the page has loaded; without scripts the whole list shows.
	let ready = $state(false);
	onMount(() => {
		ready = true;
	});

	let label = $state<GuessLabel | 'all'>('all');
	let band = $state<GuessBand | 'all'>('all');
	let query = $state('');

	const shown = $derived(filterGuesses(rows, { label, band, query }));
	const labelCounts = $derived(countBy(rows, (g) => g.label, LABELS));
	const bandCounts = $derived(countBy(rows, (g) => g.band, BANDS));
	const bandsInUse = $derived(BANDS.filter((b) => bandCounts[b] > 0));

	function clear() {
		label = 'all';
		band = 'all';
		query = '';
	}

	// The three accuracy figures share one scale that starts at zero, so the
	// bars can be compared by eye.
	const bars = $derived(
		evaluation
			? [
					{ key: 'method', name: 'This method', value: evaluation.accuracy },
					{ key: 'name', name: 'Name shape only', value: evaluation.baselines.name_only_accuracy },
					{
						key: 'majority',
						name: `Always "${labelText(evaluation.baselines.majority_label).toLowerCase()}"`,
						value: evaluation.baselines.majority_accuracy
					}
				]
			: []
	);

	const versusName = $derived(
		evaluation ? gainText(evaluation.accuracy, evaluation.baselines.name_only_accuracy) : null
	);
	const versusMajority = $derived(
		evaluation ? gainText(evaluation.accuracy, evaluation.baselines.majority_accuracy) : null
	);

	const unvalidatedLabels = $derived(
		evaluation ? evaluation.per_label.filter((l) => !l.validated).map((l) => labelText(l.label)) : []
	);
</script>

<svelte:head>
	<title>Name Guesses · APT Explorer</title>
	<meta
		name="description"
		content="A program's guesses at what each unresolved name in the CCS '25 data is, with the measured accuracy of the method. Every guess is pending confirmation."
	/>
</svelte:head>

<div class="intro">
	<h1>Name Guesses</h1>
	<p class="banner" role="note">
		<strong>Pending confirmation.</strong> Every label on this page is a guess made by a program. None of
		them changes an actor, an alias, a report link or a match rate anywhere else on this site.
	</p>
	<p class="lede">
		Some names in the paper's reports match no actor in the registry. This page gives each one a
		label (actor, malware, tool or not an entity) and, for a probable actor, the closest known actor.
		The program compares each name with the names the sources already list. To learn how far to trust
		it, we hid each known name in turn and asked the program to recover its label. Those results come
		first, and they are modest.
	</p>
	<p class="jump"><a href="#guess-list">Go to the guesses</a></p>
</div>

<section id="evaluation" aria-labelledby="evaluation-heading">
	<h2 id="evaluation-heading">How Good Are the Guesses</h2>
	{#if evaluation == null}
		<p class="empty">
			Too few names have a known answer in this build to measure the method, so it makes no guesses.
		</p>
	{:else}
		<p>
			The method was scored on {formatCount(evaluation.ground_truth.n)} names whose answer a source
			already lists. Each was treated as if it were unresolved, with its own entry hidden from the
			reference. The label was right for {formatCount(evaluation.correct)} of them.
		</p>
		<p class="rate">
			<span class="data big">{percentText(evaluation.accuracy)}</span>
			<span class="of">of labels were right</span>
		</p>

		<ul class="accuracy" aria-label="Accuracy of the method and of two plain alternatives">
			{#each bars as b (b.key)}
				<li>
					<span class="bar-name">{b.name}</span>
					<span
						class="track"
						role="img"
						aria-label="{b.name}: {percentText(b.value)}"
					>
						<span class="fill {b.key}" style:width="{(b.value ?? 0) * 100}%"></span>
					</span>
					<span class="data bar-value">{percentText(b.value)}</span>
				</li>
			{/each}
		</ul>
		<p class="section-note">
			{#if versusMajority != null}
				The method is {versusMajority} the answer that always gives the most common label{versusName !=
				null
					? `, and ${versusName} a version that uses only the shape of the name`
					: ''}.
			{/if}
			The names are few, so a gap of a few points is within noise. The method helps most where it
			says High, as the next table shows.
		</p>

		<h3>Confidence</h3>
		<p>
			Each actor or malware guess carries a confidence. It is the share of scored names with a
			similar score that the method labelled correctly. High means 0.85 or more and medium means
			0.70 or more. A guess that rests on no measured signal is always low.
		</p>
		<div class="scroll">
			<table>
				<thead>
					<tr>
						<th scope="col">Band</th>
						<th scope="col" class="num">Scored names</th>
						<th scope="col" class="num">Correct</th>
						<th scope="col" class="num">Share correct</th>
					</tr>
				</thead>
				<tbody>
					{#each evaluation.bands as b (b.band)}
						<tr>
							<th scope="row">{bandText(b.band)}</th>
							<td class="num data">{formatCount(b.n)}</td>
							<td class="num data">{formatCount(b.correct)}</td>
							<td class="num data">{percentText(b.precision)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<h3>By Label</h3>
		<p>
			Precision is the share of names given a label that truly carry it. Recall is the share of
			names that truly carry the label and were given it.
			{#if unvalidatedLabels.length > 0}
				No known name is labelled {unvalidatedLabels.join(' or ').toLowerCase()} in enough numbers to
				test, so guesses with {unvalidatedLabels.length === 1 ? 'that label' : 'those labels'} are shown
				as unvalidated and carry no confidence.
			{/if}
		</p>
		<div class="scroll">
			<table>
				<thead>
					<tr>
						<th scope="col">Label</th>
						<th scope="col" class="num">Known names</th>
						<th scope="col" class="num">Guessed</th>
						<th scope="col" class="num">Precision</th>
						<th scope="col" class="num">Recall</th>
					</tr>
				</thead>
				<tbody>
					{#each evaluation.per_label as l (l.label)}
						<tr>
							<th scope="row">
								{labelText(l.label)}
								{#if !l.validated}<span class="tag">unvalidated</span>{/if}
							</th>
							<td class="num data">{formatCount(l.support)}</td>
							<td class="num data">{formatCount(l.predicted)}</td>
							<td class="num data">{percentText(l.precision)}</td>
							<td class="num data">{percentText(l.recall)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<h3>Confusion</h3>
		<p>
			Each row is the known label and each column is the label the method gave. The diagonal holds
			the correct answers.
		</p>
		<div class="scroll">
			<table class="confusion">
				<thead>
					<tr>
						<th scope="col"><span class="visually-hidden">Known label</span></th>
						{#each evaluation.confusion.labels as l (l)}
							<th scope="col" class="num">{labelText(l)}</th>
						{/each}
					</tr>
				</thead>
				<tbody>
					{#each evaluation.confusion.rows as r, i (i)}
						<tr>
							<th scope="row">{labelText(evaluation.confusion.labels[i])}</th>
							{#each r as n, j (j)}
								<td class="num data" class:diagonal={i === j}>{formatCount(n)}</td>
							{/each}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<h3>Matches to a Known Actor</h3>
		<p>
			For a name labelled actor, the method also looks for the closest known actor. Of the
			{formatCount(evaluation.matching.actor_names)} known actor names,
			{formatCount(evaluation.matching.matchable)} have another name in the registry that a match could
			find. A kind of match is shown on a guess only when it was right at least half the time here.
		</p>
		<div class="scroll">
			<table>
				<thead>
					<tr>
						<th scope="col">Kind of match</th>
						<th scope="col" class="num">Proposed</th>
						<th scope="col" class="num">Right</th>
						<th scope="col" class="num">Share right</th>
						<th scope="col">Shown</th>
					</tr>
				</thead>
				<tbody>
					{#each evaluation.matching.by_kind as k (k.kind)}
						<tr>
							<th scope="row">{kindText(k.kind)}</th>
							<td class="num data">{formatCount(k.proposed)}</td>
							<td class="num data">{formatCount(k.correct)}</td>
							<td class="num data">{percentText(k.precision)}</td>
							<td>{k.published ? 'Yes' : 'No'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>

		<h3>Signals</h3>
		<p>
			A signal is one thing the program checks about a name. A signal is kept only when the model
			does worse without it. The weight says how strongly a kept signal pushes toward its label.
		</p>
		<ul class="signals">
			{#each evaluation.signals as s (s.signal)}
				<li>
					<p class="signal-head">
						<code>{s.signal}</code>
						<span class="tag" class:kept={s.kept}>{s.kept ? 'kept' : 'dropped'}</span>
					</p>
					<p class="signal-text">{s.description}</p>
					<p class="signal-facts data">
						fires on {formatCount(s.fires)}{s.implied_label
							? `, mostly ${labelText(s.implied_label).toLowerCase()}`
							: ''}{s.precision_when_fires != null
							? `, right ${percentText(s.precision_when_fires)}`
							: ''}{s.weight != null ? `, weight ${s.weight.toFixed(1)}` : ''}
					</p>
					<p class="signal-note">{s.note}</p>
				</li>
			{/each}
			{#each evaluation.unmeasured_signals as u (u.signal)}
				<li>
					<p class="signal-head">
						<code>{u.signal}</code>
						<span class="tag">not measured</span>
					</p>
					<p class="signal-note">{u.reason}</p>
				</li>
			{/each}
		</ul>

		<h3>Limitations</h3>
		<ul class="limits">
			{#each evaluation.limitations as l (l)}
				<li>{l}</li>
			{/each}
			<li>
				Three fixed rules set some labels without any measurement: a placeholder word such as
				"unclassified", the word "operation" or "campaign", and an alias that a source lists for an
				actor and never for software. Those guesses are shown as unvalidated.
			</li>
			<li>
				Names that differ only by a suffix or a plural can look like the same actor when they are
				not. A proposed actor is a lead to check, not an identification.
			</li>
		</ul>
	{/if}
</section>

<section id="guess-list" aria-labelledby="guess-list-heading">
	<h2 id="guess-list-heading">The Guesses</h2>
	{#if rows.length === 0}
		<p class="empty">
			{evaluation == null
				? 'No guesses are made in this build, because the method could not be measured.'
				: 'No unresolved name needs a guess in this build.'}
		</p>
	{:else}
		<p>
			{formatCount(rows.length)}
			{rows.length === 1 ? 'name resolves' : 'names resolve'} to no actor, the most often seen first. Open
			a row to read the evidence behind its label.
		</p>

		{#if ready}
			<form class="filters" onsubmit={(e) => e.preventDefault()}>
				<label>
					<span class="field">Label</span>
					<select bind:value={label}>
						<option value="all">All ({formatCount(rows.length)})</option>
						{#each LABELS as l (l)}
							<option value={l}>{labelText(l)} ({formatCount(labelCounts[l])})</option>
						{/each}
					</select>
				</label>
				<label>
					<span class="field">Confidence</span>
					<select bind:value={band}>
						<option value="all">All ({formatCount(rows.length)})</option>
						{#each bandsInUse as b (b)}
							<option value={b}>{bandText(b)} ({formatCount(bandCounts[b])})</option>
						{/each}
					</select>
				</label>
				<label class="search">
					<span class="field">Search</span>
					<input type="search" bind:value={query} placeholder="Name or matched actor" />
				</label>
			</form>
			<p class="count" aria-live="polite">
				Showing {formatCount(shown.length)} of {formatCount(rows.length)}
			</p>
		{/if}

		{#if shown.length === 0}
			<p class="empty">
				No guess matches these filters.
				<button type="button" class="link" onclick={clear}>Clear the filters</button>
			</p>
		{:else}
			<ol class="guesses">
				{#each shown as g (g.name)}
					<li class="guess">
						<div class="head">
							<span class="name">{g.name}</span>
							<span class="data seen">{formatCount(g.count)} {g.count === 1 ? 'report' : 'reports'}</span>
						</div>
						<p class="verdict">
							<span class="label-pill {g.label}">{labelText(g.label)}</span>
							<span class="conf {g.band}">{confidenceText(g)}</span>
							<span class="status">{g.status}</span>
						</p>
						{#if g.matched_actor_id != null}
							<p class="match">
								Closest known actor:
								<a href="{base}/actors/{g.matched_actor_id}/">{g.matched_actor_name ?? g.matched_actor_id}</a>
							</p>
						{/if}
						{#if g.evidence.length > 0}
							<details>
								<summary>
									Evidence ({g.evidence.length})
								</summary>
								<ul class="evidence">
									{#each g.evidence as e, i (i)}
										<li>
											<span class="detail">{e.detail}</span>
											<span class="weight data">{weightText(e.weight)}</span>
										</li>
									{/each}
								</ul>
							</details>
						{/if}
					</li>
				{/each}
			</ol>
		{/if}
	{/if}
</section>

<style>
	.intro,
	section > p,
	section > .limits,
	section > .signals {
		max-width: 44rem;
	}

	.lede {
		font-size: 1.125rem;
	}

	.jump {
		font-size: 0.9375rem;
	}

	/* The banner has to read as a caution in every theme, so it takes its
	   colour from the danger token and not from the accent used for links. */
	.banner {
		max-width: 44rem;
		margin: 1rem 0;
		padding: 0.75rem 1rem;
		background: var(--surface);
		border: 1px solid var(--danger);
		border-left-width: 0.375rem;
		border-radius: 0.5rem;
	}

	.section-note,
	.count,
	.signal-note,
	.signal-facts {
		color: var(--text-muted);
		font-size: 0.9375rem;
	}

	h3 {
		margin-top: 2rem;
	}

	.rate {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.75rem;
	}

	.big {
		color: var(--accent);
		font-size: 2.25rem;
		font-weight: 600;
		line-height: 1;
	}

	.of {
		color: var(--text-muted);
	}

	.accuracy {
		display: grid;
		gap: 0.625rem;
		max-width: 44rem;
		margin: 1rem 0;
		padding: 0;
		list-style: none;
	}

	.accuracy li {
		display: grid;
		grid-template-columns: 8.5rem minmax(0, 1fr) 3rem;
		align-items: center;
		gap: 0.75rem;
	}

	@media (max-width: 30rem) {
		.accuracy li {
			grid-template-columns: minmax(0, 1fr) 3rem;
		}

		.accuracy .bar-name {
			grid-column: 1 / -1;
		}
	}

	.bar-name {
		font-size: 0.9375rem;
	}

	.bar-value {
		text-align: right;
		font-size: 0.875rem;
	}

	.track {
		display: block;
		height: 0.75rem;
		overflow: hidden;
		border-radius: 999px;
		background: var(--border);
	}

	.fill {
		display: block;
		height: 100%;
	}

	.fill.method {
		background: var(--accent);
	}

	.fill.name {
		background: var(--accent-2);
	}

	.fill.majority {
		background: var(--rule-2);
	}

	.scroll {
		max-width: 44rem;
		overflow-x: auto;
	}

	table {
		width: 100%;
		margin: 1rem 0;
		border-collapse: collapse;
		font-size: 0.9375rem;
	}

	th,
	td {
		padding: 0.5rem 0.75rem 0.5rem 0;
		border-bottom: 1px solid var(--border);
		text-align: left;
		vertical-align: top;
		/* Every cell here is a short label or a number. The page default of
		   breaking anywhere would cut "Malware" into pieces, so a narrow table
		   scrolls in its own box instead. */
		overflow-wrap: normal;
	}

	thead th {
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		font-weight: 500;
		/* A heading wraps between words and never inside one. */
		letter-spacing: 0.02em;
		text-transform: uppercase;
	}

	tbody th {
		font-weight: 500;
	}

	.num {
		text-align: right;
		padding-right: 0.75rem;
	}

	.diagonal {
		color: var(--accent);
		font-weight: 600;
	}

	.visually-hidden {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
		white-space: nowrap;
	}

	.tag {
		display: inline-block;
		margin-left: 0.375rem;
		padding: 0 0.375rem;
		border: 1px solid var(--border);
		border-radius: 999px;
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		font-weight: 400;
	}

	.tag.kept {
		border-color: var(--accent-2);
		color: var(--accent-2);
	}

	.signals,
	.limits {
		margin: 0 0 1rem;
		padding-left: 0;
		list-style: none;
	}

	.limits {
		padding-left: 1.5rem;
		list-style: disc;
	}

	.limits li {
		margin-bottom: 0.5rem;
	}

	.signals li {
		padding: 0.625rem 0;
		border-bottom: 1px solid var(--border);
	}

	.signals p {
		margin: 0.125rem 0;
		overflow-wrap: anywhere;
	}

	.signal-head code {
		color: var(--accent);
	}

	.signal-facts {
		font-size: 0.75rem;
	}

	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem 1rem;
		margin: 1rem 0 0.5rem;
	}

	.filters label {
		display: grid;
		gap: 0.25rem;
		min-width: 0;
	}

	.field {
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		letter-spacing: 0.06em;
		text-transform: uppercase;
	}

	.filters select,
	.filters input {
		min-height: 2.5rem;
		padding: 0.375rem 0.625rem;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 0.5rem;
		color: var(--text);
		font: inherit;
		max-width: 100%;
	}

	.search {
		flex: 1 1 14rem;
	}

	.empty {
		max-width: 44rem;
		padding: 1rem;
		border: 1px dashed var(--border);
		border-radius: 0.75rem;
		color: var(--text-muted);
	}

	.link {
		padding: 0;
		background: none;
		border: 0;
		color: var(--accent);
		font: inherit;
		text-decoration: underline;
		cursor: pointer;
	}

	.guesses {
		display: grid;
		gap: 0.625rem;
		max-width: 44rem;
		margin: 0.75rem 0 1rem;
		padding: 0;
		list-style: none;
	}

	.guess {
		padding: 0.75rem 1rem;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 0.75rem;
	}

	.head {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.25rem 1rem;
	}

	.name {
		font-weight: 600;
		overflow-wrap: anywhere;
	}

	.seen {
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	.verdict {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.375rem 0.75rem;
		margin: 0.375rem 0;
		font-size: 0.9375rem;
	}

	.label-pill {
		padding: 0.0625rem 0.5rem;
		border: 1px solid var(--accent-2);
		border-radius: 999px;
		color: var(--accent-2);
		font-size: 0.8125rem;
		font-weight: 500;
	}

	.label-pill.actor {
		border-color: var(--accent);
		color: var(--accent);
	}

	.status {
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.match {
		margin: 0.25rem 0;
		font-size: 0.9375rem;
		overflow-wrap: anywhere;
	}

	details {
		margin-top: 0.375rem;
	}

	summary {
		color: var(--accent);
		font-size: 0.9375rem;
		cursor: pointer;
	}

	.evidence {
		display: grid;
		gap: 0.5rem;
		margin: 0.5rem 0 0;
		padding: 0;
		list-style: none;
		font-size: 0.9375rem;
	}

	.evidence li {
		display: grid;
		gap: 0.125rem;
	}

	.detail {
		overflow-wrap: anywhere;
	}

	.weight {
		color: var(--text-muted);
		font-size: 0.75rem;
	}
</style>
