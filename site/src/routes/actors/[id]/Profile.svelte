<script lang="ts">
	import { base } from '$app/paths';
	import type { Actor, SourcedValue } from '$lib/data';
	import ConflictNote from '$lib/components/ConflictNote.svelte';
	import SourceBadge from '$lib/components/SourceBadge.svelte';
	import Timeline from '$lib/components/Timeline.svelte';
	import { formatCount, formatDate } from '$lib/format';
	import { countryName } from '../actors';
	import {
		actorSources,
		DATE_BASIS_LABELS,
		groupValues,
		linkNote,
		reportLinks,
		techniqueUrl,
		undatedCount,
		type ProfileReport
	} from './profile';

	// The route's +page.svelte picks between this profile and the stub for a merged slug, so this
	// component always has an actor.
	let { actor, reports }: { actor: Actor; reports: ProfileReport[] } = $props();

	const sources = $derived(actorSources(actor));
	const lastReported = $derived(reports.find((r) => r.published)?.published ?? null);

	// Each section renders only when it has something in it: an empty
	// heading reads as missing data, and "not reported" under every heading
	// of a sparse actor would bury the few facts there are.
	const attribution = $derived(
		(
			[
				{ field: 'origin', label: 'Origin', values: actor.origin },
				{ field: 'sponsor', label: 'Sponsor', values: actor.sponsor },
				{ field: 'motivation', label: 'Motivation', values: actor.motivation }
			] as const
		).filter((f) => f.values.length > 0 || actor.conflicts.some((c) => c.field === f.field))
	);
	const targets = $derived(actor.claimed_targets);
	const hasTargets = $derived(targets.countries.length > 0 || targets.sectors.length > 0);
	const malware = $derived(groupValues(actor.malware.map((m) => ({ value: m.name, source: m.source }))));
	const documented = $derived(new Set(actor.techniques_documented));
	const hasTechniques = $derived(actor.techniques_documented.length > 0 || actor.techniques_reported.length > 0);

	// The newest reports show at once; the rest sit behind a native
	// <details>, which opens without scripts, so a busy actor's page starts
	// with its profile rather than three hundred rows.
	const FIRST_REPORTS = 20;
	const firstReports = $derived(reports.slice(0, FIRST_REPORTS));
	const moreReports = $derived(reports.slice(FIRST_REPORTS));

	const show = (field: string, value: string) => (field === 'origin' ? countryName(value) : value);
</script>

<svelte:head>
	<title>{actor.name} · Actors · APT Explorer</title>
	<meta
		name="description"
		content="{actor.name}: aliases with their sources, attribution claims and {actor.reports.length === 1
			? '1 linked report'
			: `${formatCount(actor.reports.length)} linked reports`}."
	/>
</svelte:head>

{#snippet valueList(values: readonly SourcedValue[], field: string)}
	<ul class="values">
		{#each groupValues(values) as g}
			<li>
				<span class="value">{show(field, g.value)}</span>
				<span class="badges"
					><span class="visually-hidden">from </span>{#each g.sources as s}<SourceBadge source={s} />{/each}</span
				>
			</li>
		{/each}
	</ul>
{/snippet}

{#snippet reportItem(r: ProfileReport)}
	{@const links = reportLinks(r)}
	{@const note = linkNote(links)}
	<li class="report">
		<p class="report-title">
			{#if links.primary}
				<a href={links.primary.href}>{r.title}</a>
			{:else}
				{r.title}
			{/if}
		</p>
		<p class="report-meta">
			{#if r.published}
				<time class="data" datetime={r.published}>{formatDate(r.published)}</time>
				<span class="basis">{DATE_BASIS_LABELS[r.date_basis]}</span>
			{:else}
				<span>Undated</span>
			{/if}
			{#if r.organisation}<span class="org">{r.organisation}</span>{/if}
			<span class="badges"
				><span class="visually-hidden">from </span>{#each r.sources as s}<SourceBadge
						source={s}
						link={false}
					/>{/each}</span
			>
		</p>
		<p class="report-links">
			{#if note}
				<span class:warn={links.failed !== null}>{note}</span>
			{/if}
			{#if links.secondary}
				<a href={links.secondary.href}>{links.secondary.label}</a>
			{/if}
			<a href="{base}/explore/?report={encodeURIComponent(r.id)}"
				>Details<span class="visually-hidden"> for {r.title}</span></a
			>
		</p>
	</li>
{/snippet}

<header class="head">
	<p class="crumbs"><a href="{base}/actors/">All actors</a></p>
	<h1>{actor.name}</h1>
	<dl class="facts">
		<div>
			<dt>ID</dt>
			<dd class="data">{actor.id}</dd>
		</div>
		<div>
			<dt>Reports</dt>
			<dd>
				{#if reports.length > 0}
					<a href="#reports">{formatCount(actor.reports.length)}</a>
				{:else}
					none linked
				{/if}
			</dd>
		</div>
		{#if lastReported}
			<div>
				<dt>Last reported</dt>
				<dd><time class="data" datetime={lastReported}>{formatDate(lastReported)}</time></dd>
			</div>
		{/if}
		<div>
			<dt>Sources</dt>
			<dd class="badges">{#each sources as s}<SourceBadge source={s} />{/each}</dd>
		</div>
		<div>
			<dt>Merge evidence</dt>
			<dd>
				<a href="{base}/methodology/"
					>{actor.evidence_count === 1 ? '1 alias match' : `${formatCount(actor.evidence_count)} alias matches`}</a
				>
			</dd>
		</div>
	</dl>
	{#if reports.length === 0}
		<p class="no-reports">
			No published report is linked to this actor yet. A report is linked when Malpedia, MITRE
			ATT&CK® or the CCS '25 data connects it to the actor.
		</p>
	{/if}
</header>

<section aria-labelledby="aliases-heading">
	<h2 id="aliases-heading">Aliases</h2>
	<ul class="aliases" aria-labelledby="aliases-heading">
		{#each actor.aliases as a}
			<li>
				<span class="alias">{a.value}</span>
				<span class="badges"
					><span class="visually-hidden">from </span>{#each a.sources as s}<SourceBadge source={s} />{/each}</span
				>
			</li>
		{/each}
	</ul>
</section>

{#if attribution.length > 0}
	<section aria-labelledby="attribution-heading">
		<h2 id="attribution-heading">Origin, Sponsor and Motivation</h2>
		<dl class="claims">
			{#each attribution as f (f.field)}
				<div>
					<dt>{f.label}</dt>
					<dd>
						{#if f.values.length > 0}{@render valueList(f.values, f.field)}{/if}
						{#each actor.conflicts.filter((c) => c.field === f.field) as c}
							<ConflictNote conflict={c} display={f.field === 'origin' ? countryName : undefined} />
						{/each}
					</dd>
				</div>
			{/each}
		</dl>
	</section>
{/if}

{#if actor.timeline.length > 0}
	<section aria-labelledby="timeline-heading">
		<h2 id="timeline-heading">Reporting Timeline</h2>
		<Timeline points={actor.timeline} undated={undatedCount(actor)} />
	</section>
{/if}

{#if hasTargets}
	<section aria-labelledby="targets-heading">
		<h2 id="targets-heading">Claimed targets (actor-level, per source)</h2>
		<p class="section-note">
			Sources give these countries and sectors for the actor as a whole. They do not say which
			report or campaign hit which target.
		</p>
		<dl class="claims">
			{#if targets.countries.length > 0}
				<div>
					<dt>Countries</dt>
					<dd>{@render valueList(targets.countries, 'origin')}</dd>
				</div>
			{/if}
			{#if targets.sectors.length > 0}
				<div>
					<dt>Sectors</dt>
					<dd>{@render valueList(targets.sectors, 'sector')}</dd>
				</div>
			{/if}
		</dl>
	</section>
{/if}

{#if malware.length > 0}
	<section aria-labelledby="malware-heading">
		<h2 id="malware-heading">Malware and Tools</h2>
		<ul class="values">
			{#each malware as m}
				<li>
					<span class="value">{m.value}</span>
					<span class="badges"
						><span class="visually-hidden">from </span>{#each m.sources as s}<SourceBadge source={s} />{/each}</span
					>
				</li>
			{/each}
		</ul>
	</section>
{/if}

{#if hasTechniques}
	<section aria-labelledby="techniques-heading">
		<h2 id="techniques-heading">Techniques</h2>
		<div class="techniques">
			{#if actor.techniques_documented.length > 0}
				<div>
					<h3>Documented by MITRE ATT&CK</h3>
					<ul class="ids">
						{#each actor.techniques_documented as id}
							<li><a class="data" href={techniqueUrl(id)}>{id}</a></li>
						{/each}
					</ul>
				</div>
			{/if}
			{#if actor.techniques_reported.length > 0}
				<div>
					<h3>Named in recent reports</h3>
					<ul class="ids">
						{#each actor.techniques_reported as t}
							<li>
								<a class="data" href={techniqueUrl(t.id)}>{t.id}</a>
								<span class="n">{t.count === 1 ? '1 report' : `${formatCount(t.count)} reports`}</span>
								{#if documented.size > 0 && !documented.has(t.id)}<span class="tag">reports only</span>{/if}
							</li>
						{/each}
					</ul>
				</div>
			{/if}
		</div>
		{#if actor.techniques_reported.length > 0}
			<p class="section-note">
				Report counts come from technique IDs found in the text of the actor's reports from the
				last two years, counted in whole quarters.
				{#if documented.size > 0}“Reports only” marks a technique that recent reports name but MITRE
					ATT&CK® does not list for this actor.{/if}
			</p>
		{/if}
	</section>
{/if}

{#if actor.cves.length > 0}
	<section aria-labelledby="cves-heading">
		<h2 id="cves-heading">CVEs Named in Reports</h2>
		<ul class="ids cves">
			{#each actor.cves as c}
				<li>
					<a class="data" href="{base}/explore/?cve={c.cve}">{c.cve}</a>
					{#if c.kev}<span class="tag kev">KEV</span>{/if}
					{#if c.ransomware}<span class="tag">ransomware</span>{/if}
				</li>
			{/each}
		</ul>
		<p class="section-note">
			KEV marks a CVE in CISA's Known Exploited Vulnerabilities Catalog, and “ransomware” marks one
			that the catalogue records as used in ransomware campaigns.
		</p>
	</section>
{/if}

{#if reports.length > 0}
	<section id="reports" aria-labelledby="reports-heading">
		<h2 id="reports-heading">Reports</h2>
		<p class="section-note">
			{reports.length === 1 ? '1 report' : `${formatCount(reports.length)} reports`}, newest first. A
			title opens the publisher's copy, and Details opens the report in
			<a href="{base}/explore/?actor={encodeURIComponent(actor.id)}">Explore</a>.
		</p>
		<ol class="reports" aria-labelledby="reports-heading">
			{#each firstReports as r (r.id)}{@render reportItem(r)}{/each}
		</ol>
		{#if moreReports.length > 0}
			<details class="more">
				<summary>Show all {formatCount(reports.length)} reports</summary>
				<ol class="reports" start={FIRST_REPORTS + 1} aria-label="Older reports">
					{#each moreReports as r (r.id)}{@render reportItem(r)}{/each}
				</ol>
			</details>
		{/if}
	</section>
{/if}

<style>
	.head {
		max-width: 56rem;
	}

	.crumbs {
		margin: 0 0 0.5rem;
		font-size: 0.875rem;
	}

	.crumbs a::before {
		content: '← ';
	}

	h1 {
		overflow-wrap: anywhere;
	}

	.facts {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem 2rem;
		margin: 0;
	}

	.facts > div {
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
	}

	.facts dd {
		font-size: 0.9375rem;
	}

	.facts .data {
		font-size: 0.8125rem;
	}

	.no-reports {
		max-width: 44rem;
		margin: 1.25rem 0 0;
		color: var(--text-muted);
	}

	section {
		max-width: 56rem;
	}

	.section-note {
		max-width: 44rem;
		color: var(--text-muted);
		font-size: 0.9375rem;
	}

	/* Badges and the value they belong to stay together; a value that is
	   one long unbroken string wraps inside its row instead of pushing it
	   wider. Flex and grid children need min-width: 0 for that, because
	   their default minimum is the width of the longest word. */
	.badges {
		display: inline-flex;
		flex-wrap: wrap;
		gap: 0.25rem;
		vertical-align: baseline;
	}

	.aliases {
		display: grid;
		gap: 0.375rem 2rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	/* Some actors have forty aliases; two columns halve the scroll on a
	   wide screen, and a long alias still wraps inside its column. */
	@media (min-width: 52rem) {
		.aliases {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	.aliases li {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.625rem;
		min-width: 0;
		padding: 0.375rem 0;
		border-bottom: 1px solid var(--border);
	}

	.alias {
		min-width: 0;
		max-width: 100%;
		font-weight: 550;
		overflow-wrap: anywhere;
	}

	.values {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1.25rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.values li {
		display: inline-flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.5rem;
		min-width: 0;
		max-width: 100%;
	}

	.value {
		min-width: 0;
		max-width: 100%;
		overflow-wrap: anywhere;
	}

	.claims {
		display: grid;
		gap: 1rem;
		margin: 0;
	}

	.claims > div {
		min-width: 0;
	}

	.techniques {
		display: grid;
		gap: 0.5rem 2.5rem;
	}

	@media (min-width: 52rem) {
		.techniques {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	.techniques > div {
		min-width: 0;
	}

	.techniques h3 {
		margin-top: 0.5rem;
		font-size: 0.9375rem;
		color: var(--text-muted);
	}

	.ids {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem 1rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.ids li {
		display: inline-flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.125rem 0.4375rem;
		min-width: 0;
	}


	.n {
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.tag {
		display: inline-block;
		padding: 0 0.375rem;
		border: 1px solid var(--border);
		border-radius: 0.25rem;
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		letter-spacing: 0.02em;
	}

	.tag.kev {
		border-color: var(--accent);
		color: var(--text);
		background: var(--accent-soft);
	}

	.reports {
		display: grid;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.report {
		min-width: 0;
		padding: 0.875rem 0;
		border-bottom: 1px solid var(--border);
	}

	.report p {
		margin: 0;
	}

	.report-title {
		font-weight: 550;
		overflow-wrap: anywhere;
	}

	.report-meta,
	.report-links {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.125rem 0.875rem;
		margin-top: 0.25rem !important;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.report-meta > *,
	.report-links > * {
		min-width: 0;
		overflow-wrap: anywhere;
	}

	.report-meta .data {
		font-size: 0.8125rem;
		color: var(--text);
	}

	.warn {
		color: var(--danger);
	}

	.more {
		margin-top: 0.75rem;
	}

	.more summary {
		display: inline-block;
		padding: 0.375rem 0.875rem;
		border: 1px solid var(--border);
		border-radius: 999px;
		background: var(--surface);
		color: var(--accent);
		font-weight: 550;
		cursor: pointer;
		list-style: none;
	}

	.more summary::-webkit-details-marker {
		display: none;
	}

	.more summary:hover {
		border-color: var(--accent);
	}

	.more[open] summary {
		display: none;
	}
</style>
