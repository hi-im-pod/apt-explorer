<script lang="ts">
	import { base } from '$app/paths';
	import { sourceLabel } from '$lib/data/labels';
	import { formatCount, formatDate } from '$lib/format';

	let { data } = $props();

	const views = [
		{
			path: '/explore/',
			title: 'Explore',
			text: 'Search reports and campaigns by actor, date, source, CVE and technique. The filters live in the URL, so a filtered view can be shared.'
		},
		{
			path: '/actors/',
			title: 'Actors',
			text: 'Every tracked actor, each alias with the source that gives it, and the reports that name the actor.'
		},
		{
			path: '/trends/',
			title: 'Trends',
			text: 'Reporting activity, newly documented actors and exploited vulnerabilities over the last two years.'
		}
	];
</script>

<svelte:head>
	<title>APT Explorer</title>
	<meta
		name="description"
		content="Advanced persistent threat actors, their aliases and the reports written about them, merged from open sources and rebuilt every week."
	/>
</svelte:head>

<section class="intro">
	<p class="kicker">Open-source threat intelligence</p>
	<h1>APT actors, reports and trends from open sources</h1>
	<p class="lede">
		APT Explorer follows advanced persistent threat (APT) actors across open sources. It merges each
		actor's aliases from MITRE ATT&CK®, the MISP galaxy, ETDA and Malpedia, and records the evidence
		behind each merge. Each actor links to the reports written about it, and the data is rebuilt
		every week.
	</p>
	<p class="credit">
		Built on the dataset of Yuldoshkhujaev et al. (CCS '25). <a href="{base}/about/#paper-heading"
			>About has the full credit</a
		>.
	</p>
</section>

<section aria-labelledby="views-heading">
	<h2 id="views-heading">Views</h2>
	<ul class="views">
		{#each views as view (view.path)}
			<li>
				<a href="{base}{view.path}">
					<span class="view-title">{view.title}<span class="arrow" aria-hidden="true">→</span></span>
					<span class="view-text">{view.text}</span>
				</a>
			</li>
		{/each}
	</ul>
</section>

<section aria-labelledby="source-health-heading">
	<h2 id="source-health-heading">Source Health</h2>
	<p class="section-note">
		Each source is fetched every week. When a fetch fails, the build keeps the last good snapshot and
		marks the source stale. <a href="{base}/about/">Sources and licences</a> lists what each source
		allows.
	</p>
	<ul class="health" aria-labelledby="source-health-heading">
		{#each data.sources as s (s.name)}
			<li class:stale={s.stale}>
				<span class="name">{sourceLabel(s.name).name}</span>
				<span class="status"
					><span class="dot" aria-hidden="true"></span>{s.stale ? 'Stale' : 'Current'}</span
				>
				<span class="detail">
					Last good fetch
					{#if s.last_success}<time datetime={s.last_success}>{formatDate(s.last_success)}</time
						>{:else}never{/if}
					· <span class="data">{formatCount(s.record_count)}</span> records
				</span>
			</li>
		{/each}
	</ul>
</section>

<style>
	.intro {
		max-width: 46rem;
	}

	.kicker {
		margin: 0 0 0.75rem;
		color: var(--accent);
		font-family: var(--font-data);
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}

	.lede {
		color: var(--text-muted);
		font-size: 1.125rem;
		max-width: 42rem;
	}

	.credit {
		max-width: 42rem;
		color: var(--text-muted);
	}

	.section-note {
		max-width: 42rem;
		color: var(--text-muted);
	}

	.views,
	.health {
		display: grid;
		gap: 0.75rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	@media (min-width: 45rem) {
		.views {
			grid-template-columns: repeat(3, 1fr);
		}
		.health {
			grid-template-columns: repeat(2, 1fr);
		}
	}

	.views a {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		height: 100%;
		padding: 1.125rem 1.25rem;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 0.75rem;
		color: var(--text);
		text-decoration: none;
	}

	.views a:hover {
		border-color: var(--accent);
	}

	.view-title {
		display: flex;
		justify-content: space-between;
		color: var(--accent);
		font-size: 1.125rem;
		font-weight: 650;
	}

	.view-text {
		color: var(--text-muted);
		font-size: 0.9375rem;
	}

	.health li {
		display: grid;
		grid-template-columns: 1fr auto;
		gap: 0.125rem 1rem;
		padding: 0.75rem 1rem;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 0.625rem;
	}

	.health .name {
		font-weight: 600;
	}

	.health .status {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		font-family: var(--font-data);
		font-size: 0.75rem;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--accent-2);
	}

	.health .dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		background: currentColor;
	}

	.health .stale {
		border-color: var(--danger);
	}

	.health .stale .status {
		color: var(--danger);
	}

	.health .detail {
		grid-column: 1 / -1;
		color: var(--text-muted);
		font-size: 0.875rem;
	}
</style>
