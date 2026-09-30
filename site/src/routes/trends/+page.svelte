<!--
	Trends: recent reporting, computed by the pipeline over the trailing 24
	months, in whole quarters starting at window_start, in six sections, each with its counting rule from
	trends.json printed beneath it.

	The headings, notes, tables and lists are prerendered, so they read
	without scripts. The charts are drawn in the browser (see Chart.svelte),
	and each has its numbers in a table as well.

	Actor names are plain text here: a link to an actor page from a
	prerendered page is followed at build time, and the actor pages are
	built on another branch.
-->
<script lang="ts">
	import { base } from '$app/paths';
	import Chart from '$lib/components/Chart.svelte';
	import type { KevActorLink } from '$lib/data/types';
	import { sourceLabel } from '$lib/data/labels';
	import { formatCount, formatDate } from '$lib/format';
	import {
		KEV_HEIGHT,
		NEW_ACTORS_HEIGHT,
		activityChart,
		activityHeight,
		kevChart,
		newActorsChart,
		techniqueChart,
		techniqueHeight
	} from './charts';
	import { kevMonthly, newActorMonths, reportedVsDocumented, reportingActivity } from './series';

	let { data } = $props();

	/** How many actors each ranked chart shows. */
	const TOP_ACTIVITY = 6;
	const TOP_TECHNIQUES = 15;

	const t = $derived(data.trends);
	const name = (id: string) => data.names[id] ?? id;
	const since = $derived(formatDate(t.window_start));

	const activity = $derived(reportingActivity(t, TOP_ACTIVITY));
	const activityPlot = $derived(activityChart(activity, data.names));
	// The same top the chart uses for its shared scale.
	const activityTop = $derived(Math.max(1, ...activity.points.map((p) => Math.max(p.count, p.prev))));
	const activityRows = $derived(activity.points.filter((p) => p.count > 0 || p.prev > 0));

	const kev = $derived(kevMonthly(t));
	const kevPlot = $derived(kevChart(kev));

	const techniques = $derived(reportedVsDocumented(t, TOP_TECHNIQUES));
	const techniquePlot = $derived(techniqueChart(techniques, data.names));

	const newActors = $derived([...t.new_actors].sort((a, b) => (a.first_seen < b.first_seen ? 1 : -1)));
	const newMonths = $derived(newActorMonths(t));
	const newPlot = $derived(newActorsChart(newMonths));
	// New actors from a single month make a one-bar chart, which says no more
	// than the list does, so the chart appears only once they spread out.
	const chartNewActors = $derived(newMonths.filter((m) => m.count > 0).length >= 2);

	/** Newest CVE first: by year, then by number, since the numbers vary in length. */
	function byCveDesc(a: KevActorLink, b: KevActorLink): number {
		const [, ay, an] = a.cve.split('-').map(Number);
		const [, by, bn] = b.cve.split('-').map(Number);
		return by - ay || bn - an;
	}
	const kevLinks = $derived([...t.kev_actor_links].sort(byCveDesc));

	function basisText(basis: string): string {
		return basis === 'report' ? 'from its earliest dated report' : `in ${sourceLabel(basis).name}`;
	}

	/** "2024-05" to "May 2024". */
	const monthName = (m: string) => formatDate(`${m}-01`).replace(/^1 /, '');
	/** "2024-Q2" to "Q2 2024". */
	const quarterName = (q: string) => `${q.slice(5)} ${q.slice(0, 4)}`;
</script>

<svelte:head>
	<title>Trends · APT Explorer</title>
	<meta
		name="description"
		content="Reporting activity, newly documented actors and exploited vulnerabilities over the last two years, recomputed every week from open sources."
	/>
</svelte:head>

<div class="intro">
	<h1>Trends</h1>
	<p class="lede">
		What current sources report over the last two years, counted in whole quarters from {since}: which actors are being written about, which are
		new, and which exploited vulnerabilities appear in reports. The figures are recomputed with every
		weekly build; these were computed on
		<time datetime={t.generated_at}>{formatDate(t.generated_at)}</time>. Each chart's counting rule
		is printed beneath it.
	</p>
</div>

<section id="reporting-activity" aria-labelledby="h-reporting-activity">
	<h2 id="h-reporting-activity">Reporting Activity</h2>
	{#if activity.actors.length}
		<p class="lead">
			The {activity.actors.length} actors with the most reports since {since}, quarter by quarter.
			All the small charts share one scale, which runs from 0 to {activityTop} reports.
		</p>
		<Chart
			title="Reports per quarter for the {activity.actors.length} most reported actors, with the same quarter a year earlier"
			note={t.notes.reporting_activity}
			plot={activityPlot}
			height={activityHeight(activity.actors.length)}
			axis="time"
			legend={[
				{ label: 'Reports in the quarter', token: '--chart-2' },
				{ label: 'Same quarter a year earlier', token: '--text', shape: 'rule' }
			]}
		>
			{#snippet table()}
				<table class="numbers">
					<thead>
						<tr>
							<th scope="col">Actor</th>
							<th scope="col">Quarter</th>
							<th scope="col" class="num">Reports</th>
							<th scope="col" class="num">A year earlier</th>
						</tr>
					</thead>
					<tbody>
						{#each activityRows as p (`${p.actor} ${p.quarter}`)}
							<tr>
								<td>{name(p.actor)}</td>
								<td>{quarterName(p.quarter)}</td>
								<td class="num">{formatCount(p.count)}</td>
								<td class="num">{formatCount(p.prev)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/snippet}
		</Chart>
	{:else}
		<p class="empty">No dated report in this window is linked to an actor yet.</p>
		<p class="note">{t.notes.reporting_activity}</p>
	{/if}
</section>

<section id="new-actors" aria-labelledby="h-new-actors">
	<h2 id="h-new-actors">Newly Documented Actors</h2>
	{#if newActors.length}
		<ul class="new-actors">
			{#each newActors as a (a.actor)}
				<li>
					<span class="actor">{name(a.actor)}</span>
					<span class="meta"
						>First seen <time datetime={a.first_seen}>{formatDate(a.first_seen)}</time>, {basisText(
							a.basis
						)}</span
					>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="empty">No actor was first documented in the last twelve months.</p>
	{/if}
	{#if chartNewActors}
		<div class="after-list">
			<p class="lead">New actors per month over the same twelve months.</p>
			<Chart
				title="Newly documented actors per month over the last twelve months"
				note={t.notes.new_actors}
				plot={newPlot}
				height={NEW_ACTORS_HEIGHT}
				axis="time"
			/>
		</div>
	{:else}
		<p class="note">{t.notes.new_actors}</p>
	{/if}
</section>

<section id="kev-monthly" aria-labelledby="h-kev-monthly">
	<h2 id="h-kev-monthly">Exploited Vulnerabilities per Month</h2>
	<Chart
		title="CVEs added to CISA's KEV catalogue each month, split by known ransomware use"
		note={t.notes.kev_monthly}
		plot={kevPlot}
		height={KEV_HEIGHT}
		axis="time"
		legend={[
			{ label: 'Known ransomware use', token: '--chart-4' },
			{ label: 'Other additions', token: '--chart-2' }
		]}
	>
		{#snippet table()}
			<table class="numbers">
				<thead>
					<tr>
						<th scope="col">Month</th>
						<th scope="col" class="num">Added</th>
						<th scope="col" class="num">Known ransomware use</th>
					</tr>
				</thead>
				<tbody>
					{#each kev as p (p.month)}
						<tr>
							<td>{monthName(p.month)}</td>
							<td class="num">{formatCount(p.added)}</td>
							<td class="num">{formatCount(p.ransomware)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/snippet}
	</Chart>
</section>

<section id="kev-actor-links" aria-labelledby="h-kev-actor-links">
	<h2 id="h-kev-actor-links">Exploited Vulnerabilities in Actor Reports</h2>
	{#if kevLinks.length}
		<div class="scroll">
			<table class="numbers wide">
				<thead>
					<tr>
						<th scope="col">CVE</th>
						<th scope="col" class="actors">Actors named in the same reports</th>
					</tr>
				</thead>
				<tbody>
					{#each kevLinks as l (l.cve)}
						<tr>
							<td><a class="data" href="{base}/explore/?cve={l.cve}">{l.cve}</a></td>
							<td class="actors">{l.actors.map(name).join(', ')}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{:else}
		<p class="empty">No KEV CVE shares a report with a resolved actor in this window.</p>
	{/if}
	<p class="note">{t.notes.kev_actor_links}</p>
</section>

<section id="reported-vs-documented" aria-labelledby="h-reported-vs-documented">
	<h2 id="h-reported-vs-documented">Reported Versus Documented Techniques</h2>
	{#if techniques.length}
		<p class="lead">
			Up to {TOP_TECHNIQUES} actors, those whose recent reports name the most techniques ATT&CK does not
			list for them first.
		</p>
		<Chart
			title="Techniques in recent reports per actor, split into those ATT&CK also documents and those only reported"
			note={t.notes.reported_vs_documented}
			plot={techniquePlot}
			height={techniqueHeight(techniques.length)}
			legend={[
				{ label: 'Also documented by ATT&CK', token: '--chart-2' },
				{ label: 'Reported only', token: '--chart-4' }
			]}
		>
			{#snippet table()}
				<table class="numbers">
					<thead>
						<tr>
							<th scope="col">Actor</th>
							<th scope="col" class="num">Also documented</th>
							<th scope="col">Reported only</th>
						</tr>
					</thead>
					<tbody>
						{#each techniques as b (b.actor)}
							<tr>
								<td>{name(b.actor)}</td>
								<td class="num">{formatCount(b.overlap)}</td>
								<td class="data">{b.ids.length ? b.ids.join(', ') : 'none'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			{/snippet}
		</Chart>
	{:else}
		<p class="empty">No actor has techniques named in reports from this window yet.</p>
		<p class="note">{t.notes.reported_vs_documented}</p>
	{/if}
</section>

<section id="source-health" aria-labelledby="h-source-health">
	<h2 id="h-source-health">Source Health</h2>
	<div class="scroll">
		<table class="numbers wide">
			<thead>
				<tr>
					<th scope="col">Source</th>
					<th scope="col">Last good fetch</th>
					<th scope="col" class="num">Records</th>
					<th scope="col">Status</th>
				</tr>
			</thead>
			<tbody>
				{#each t.source_health as s (s.name)}
					<tr class:stale={s.stale}>
						<td>{sourceLabel(s.name).name}</td>
						<td>
							{#if s.last_success}<time datetime={s.last_success}>{formatDate(s.last_success)}</time
								>{:else}never{/if}
						</td>
						<td class="num">{formatCount(s.record_count)}</td>
						<td>
							<span class="status"
								><span class="dot" aria-hidden="true"></span>{s.stale ? 'Stale' : 'Current'}</span
							>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	<p class="note">{t.notes.source_health}</p>
</section>

<style>
	.intro {
		max-width: 68ch;
	}

	.lede {
		color: var(--text-muted);
		font-size: 1.1875rem;
		line-height: 1.5;
	}

	/* Each section opens on a hairline, so the page reads as a ledger of six entries. */
	section {
		margin-top: 3rem;
		padding-top: 1.25rem;
		border-top: 1px solid var(--border);
		scroll-margin-top: 1rem;
	}

	section h2 {
		margin-top: 0;
	}

	.lead {
		max-width: 68ch;
		color: var(--text-muted);
	}

	.note {
		max-width: 68ch;
		margin-top: 0.75rem;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	/* An empty section says so in a line set off by a rule. The dashed outline
	   is kept for unconfirmed name guesses. */
	.empty {
		max-width: 68ch;
		padding: 0.25rem 0 0.25rem 1rem;
		border-left: 2px solid var(--border);
		color: var(--text-muted);
	}

	.new-actors {
		margin: 0;
		padding: 0;
		border-top: 1px solid var(--text);
		list-style: none;
	}

	.after-list {
		margin-top: 1.5rem;
	}

	.new-actors li {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.125rem 1.5rem;
		padding: 0.625rem 0;
		border-bottom: 1px solid var(--border);
	}

	.new-actors .actor {
		flex: 0 0 14rem;
		max-width: 100%;
		font-weight: 600;
	}

	.new-actors .meta {
		color: var(--text-muted);
		font-size: 0.9375rem;
	}

	/* A wide table scrolls inside its own box, never the page. */
	.scroll {
		max-width: 100%;
		overflow-x: auto;
	}

	.numbers {
		border-collapse: collapse;
		font-size: 0.875rem;
		font-variant-numeric: tabular-nums;
	}

	.numbers.wide {
		width: 100%;
		font-size: 0.9375rem;
	}

	/* Dates, counts and statuses stay on one line. On a phone the table
	   then outgrows the screen and scrolls inside .scroll, which reads better
	   than a date broken in the middle of a word. */
	.numbers.wide td:first-child {
		min-width: 11rem;
	}

	.numbers.wide td:not(:first-child),
	.numbers.wide th:not(:first-child) {
		white-space: nowrap;
	}

	/* On a wide screen a list of actor names wraps between names instead of
	   stretching the table. On a phone it stays on one line and the table scrolls in its own box. */
	@media (min-width: 40rem) {
		.numbers.wide td.actors,
		.numbers.wide th.actors {
			min-width: 14rem;
			max-width: 36rem;
			white-space: normal;
		}
	}

	/* The tables inside a chart's "Show the numbers" are styled from here,
	   because the snippet renders them in this component's scope. */
	.numbers th,
	.numbers td {
		padding: 0.5rem 0.75rem;
		border-bottom: 1px solid var(--border);
		text-align: left;
		vertical-align: top;
	}

	.numbers th {
		border-bottom-color: var(--text);
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		font-weight: 500;
	}

	.numbers th:first-child,
	.numbers td:first-child {
		padding-left: 0;
	}

	.numbers .num {
		text-align: right;
	}

	.numbers td.data {
		font-family: var(--font-data);
		font-size: 0.8125rem;
	}

	.status {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.75rem;
	}

	.dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		background: currentColor;
	}

	.stale .status {
		color: var(--danger);
	}
</style>
