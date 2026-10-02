<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import type { Actor, SourceKey, SourcedValue } from '$lib/data';
	import { sourceLabel } from '$lib/data/labels';
	import ConflictNote from '$lib/components/ConflictNote.svelte';
	import SourceBadge from '$lib/components/SourceBadge.svelte';
	import Timeline from '$lib/components/Timeline.svelte';
	import { formatCount, formatDate, lastSpan } from '$lib/format';
	import { countryName } from '../actors';
	import More from './More.svelte';
	import {
		actorSources,
		DATE_BASIS_LABELS,
		documentedOnly,
		FIRST_ALIASES,
		FIRST_CHIPS,
		FIRST_REPORTS,
		FIRST_TECHNIQUES,
		groupValues,
		ledeFor,
		linkNote,
		NAME_SOURCES,
		otherSources,
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
	const lede = $derived(ledeFor(actor));
	const origins = $derived(groupValues(actor.origin).map((g) => countryName(g.value)));

	// Each section renders only when it has something in it: an empty
	// heading reads as missing data, and "not reported" under every heading
	// of a sparse actor would bury the few facts there are.
	const attribution = $derived(
		(
			[
				{ field: 'origin', label: 'Origin', values: actor.origin },
				{ field: 'motivation', label: 'Motivation', values: actor.motivation }
			] as const
		).filter((f) => f.values.length > 0 || actor.conflicts.some((c) => c.field === f.field))
	);
	const targets = $derived(actor.claimed_targets);
	const hasTargets = $derived(targets.countries.length > 0 || targets.sectors.length > 0);
	const malware = $derived(groupValues(actor.malware.map((m) => ({ value: m.name, source: m.source }))));
	const documented = $derived(new Set(actor.techniques_documented));
	const hasTechniques = $derived(actor.techniques_documented.length > 0 || actor.techniques_reported.length > 0);
	const hasMain = $derived(
		actor.timeline.length > 0 || hasTechniques || actor.cves.length > 0 || reports.length > 0
	);
	const recentTechniques = $derived(actor.techniques_reported);
	const recent = $derived(lastSpan(page.data.build?.recent_months));
	const unseen = $derived(documentedOnly(actor));

	const firstReports = $derived(reports.slice(0, FIRST_REPORTS));
	const moreReports = $derived(reports.slice(FIRST_REPORTS));

	const show = (field: string, value: string) => (field === 'origin' ? countryName(value) : value);
	const reportCount = (n: number) => (n === 1 ? '1 report' : `${formatCount(n)} reports`);
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

{#snippet valueItems(groups: { value: string; sources: readonly SourceKey[] }[], field: string)}
	{#each groups as g}
		<li>
			<span class="value">{show(field, g.value)}</span>
			<span class="badges"
				><span class="visually-hidden">from </span>{#each g.sources as s}<SourceBadge source={s} />{/each}</span
			>
		</li>
	{/each}
{/snippet}

{#snippet valueList(values: readonly SourcedValue[], field: string, noun: string)}
	{@const groups = groupValues(values)}
	<ul class="values">{@render valueItems(groups.slice(0, FIRST_CHIPS), field)}</ul>
	{#if groups.length > FIRST_CHIPS}
		<More total={groups.length} {noun}>
			<ul class="values" aria-label="More {noun}">{@render valueItems(groups.slice(FIRST_CHIPS), field)}</ul>
		</More>
	{/if}
{/snippet}

{#snippet aliasRow(a: Actor['aliases'][number])}
	<li>
		<span class="alias">{a.value}</span>
		<span class="srcs">
			<span class="visually-hidden">from </span>
			{#each NAME_SOURCES as n}
				{#if a.sources.includes(n.key)}
					<a
						class="yes"
						href="{base}/about/#source-{n.key}"
						title={sourceLabel(n.key).name}
						aria-label={sourceLabel(n.key).short}>{n.code}</a
					>
				{:else}
					<span class="no" aria-hidden="true"></span>
				{/if}
			{/each}
			{#each otherSources(a.sources) as s}<SourceBadge source={s} />{/each}
		</span>
	</li>
{/snippet}

{#snippet techniqueRow(t: { id: string; count: number })}
	<li>
		<a class="id data" href={techniqueUrl(t.id)}>{t.id}</a>
		<span class="n">{reportCount(t.count)}</span>
		{#if documented.size > 0}
			<span class="doc" class:y={documented.has(t.id)}>{documented.has(t.id) ? 'in ATT&CK' : 'reports only'}</span>
		{:else}
			<span></span>
		{/if}
	</li>
{/snippet}

{#snippet reportItem(r: ProfileReport)}
	{@const links = reportLinks(r)}
	{@const note = linkNote(links)}
	<li class="report">
		<p class="report-date">
			{#if r.published}
				<time class="data" datetime={r.published}>{formatDate(r.published)}</time>
			{:else}
				<span class="data">Undated</span>
			{/if}
		</p>
		<div class="report-body">
			<p class="report-title">
				{#if links.primary}
					<a href={links.primary.href}>{r.title}</a>
				{:else}
					{r.title}
				{/if}
			</p>
			<p class="report-meta">
				{#if r.published}<span class="basis">{DATE_BASIS_LABELS[r.date_basis]}</span>{/if}
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
		</div>
	</li>
{/snippet}

<header class="actor-head">
	<p class="crumbs"><a href="{base}/actors/">All actors</a></p>
	<h1>{actor.name}</h1>
	{#if lede}<p class="lede">{lede}</p>{/if}
	<dl class="facts">
		<div>
			<dt>Reports</dt>
			<dd>
				{#if reports.length > 0}
					<a class="num" href="#reports">{formatCount(actor.reports.length)}</a>
				{:else}
					<span class="num">0</span>
				{/if}
			</dd>
		</div>
		{#if lastReported}
			<div>
				<dt>Last reported</dt>
				<dd><time class="num" datetime={lastReported}>{formatDate(lastReported)}</time></dd>
			</div>
		{/if}
		{#if actor.cves.length > 0}
			<div>
				<dt>Known CVEs</dt>
				<dd><a class="num" href="#cves">{formatCount(actor.cves.length)}</a></dd>
			</div>
		{/if}
		{#if actor.techniques_documented.length > 0}
			<div>
				<dt>Techniques in ATT&amp;CK</dt>
				<dd><a class="num" href="#techniques">{formatCount(actor.techniques_documented.length)}</a></dd>
			</div>
		{/if}
		{#if origins.length > 0}
			<div>
				<dt>Origin</dt>
				<dd class="word">{origins.join(', ')}</dd>
			</div>
		{/if}
	</dl>
	<dl class="meta">
		<div>
			<dt>ID</dt>
			<dd class="data">{actor.id}</dd>
		</div>
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
			ATT&CK® or the CCS '25 data connects it to the actor, or when a title or the report's text names it.
		</p>
	{/if}
</header>

<div class="cols" class:solo={!hasMain}>
	<div class="main" hidden={!hasMain}>
		{#if actor.timeline.length > 0}
			<section aria-labelledby="timeline-heading">
				<h2 id="timeline-heading">Reports per quarter</h2>
				<Timeline points={actor.timeline} undated={undatedCount(actor)} />
			</section>
		{/if}

		{#if hasTechniques}
			<section id="techniques" aria-labelledby="techniques-heading">
				<h2 id="techniques-heading">
					{recentTechniques.length > 0 ? `Techniques seen in ${recent}` : 'Techniques in ATT&CK'}
				</h2>
				{#if recentTechniques.length > 0}
					<ul class="tech" aria-labelledby="techniques-heading">
						{#each recentTechniques.slice(0, FIRST_TECHNIQUES) as t (t.id)}{@render techniqueRow(t)}{/each}
					</ul>
					{#if recentTechniques.length > FIRST_TECHNIQUES}
						<More total={recentTechniques.length} noun="techniques">
							<ul class="tech more-list" aria-label="More techniques">
								{#each recentTechniques.slice(FIRST_TECHNIQUES) as t (t.id)}{@render techniqueRow(t)}{/each}
							</ul>
						</More>
					{/if}
					<p class="key">
						Counts come from technique IDs in the text of the actor's reports from {recent},
						in whole quarters.
						{#if documented.size > 0}“Reports only” means recent reports name the technique but MITRE
							ATT&CK® does not list it for this actor.{/if}
					</p>
				{/if}
				{#if unseen.length > 0}
					<h3>{recentTechniques.length > 0 ? 'Also listed by ATT&CK' : 'Listed by ATT&CK'}</h3>
					<ul class="ids">
						{#each unseen.slice(0, FIRST_CHIPS) as id}
							<li><a class="data" href={techniqueUrl(id)}>{id}</a></li>
						{/each}
					</ul>
					{#if unseen.length > FIRST_CHIPS}
						<More total={unseen.length} noun="techniques">
							<ul class="ids" aria-label="More techniques listed by ATT&CK">
								{#each unseen.slice(FIRST_CHIPS) as id}
									<li><a class="data" href={techniqueUrl(id)}>{id}</a></li>
								{/each}
							</ul>
						</More>
					{/if}
					{#if recentTechniques.length === 0}
						<p class="key">
							MITRE ATT&CK® lists these for the actor. No report from {recent} names a technique ID.
						</p>
					{/if}
				{/if}
			</section>
		{/if}

		{#if actor.cves.length > 0}
			<section id="cves" aria-labelledby="cves-heading">
				<h2 id="cves-heading">CVEs named in reports</h2>
				{#snippet cveItem(c: Actor['cves'][number])}
					<li>
						<a class="data" href="{base}/explore/?cve={c.cve}">{c.cve}</a>
						{#if c.kev}<span class="tag kev">KEV</span>{/if}
						{#if c.ransomware}<span class="tag">ransomware</span>{/if}
					</li>
				{/snippet}
				<ul class="ids cves" aria-labelledby="cves-heading">
					{#each actor.cves.slice(0, FIRST_CHIPS) as c (c.cve)}{@render cveItem(c)}{/each}
				</ul>
				{#if actor.cves.length > FIRST_CHIPS}
					<More total={actor.cves.length} noun="CVEs">
						<ul class="ids cves" aria-label="More CVEs">
							{#each actor.cves.slice(FIRST_CHIPS) as c (c.cve)}{@render cveItem(c)}{/each}
						</ul>
					</More>
				{/if}
				<p class="key">
					KEV marks a CVE in CISA's Known Exploited Vulnerabilities Catalog, and “ransomware” marks one
					that the catalogue records as used in ransomware campaigns.
				</p>
			</section>
		{/if}

		{#if reports.length > 0}
			<section id="reports" aria-labelledby="reports-heading">
				<h2 id="reports-heading">Reports</h2>
				<ol class="reports" aria-labelledby="reports-heading">
					{#each firstReports as r (r.id)}{@render reportItem(r)}{/each}
				</ol>
				{#if moreReports.length > 0}
					<More total={reports.length} noun="reports">
						<ol class="reports continued" start={FIRST_REPORTS + 1} aria-label="Older reports">
							{#each moreReports as r (r.id)}{@render reportItem(r)}{/each}
						</ol>
					</More>
				{/if}
				<p class="key">
					{reports.length === 1 ? '1 report' : `${formatCount(reports.length)} reports`}, newest first. A
					title opens the publisher's copy, and Details opens the report in
					<a href="{base}/explore/?actor={encodeURIComponent(actor.id)}">Explore</a>.
				</p>
			</section>
		{/if}
	</div>

	<aside class="side">
		<section aria-labelledby="aliases-heading">
			<h2 id="aliases-heading">Names and who uses them</h2>
			<ul class="alias-list" aria-labelledby="aliases-heading">
				{#each actor.aliases.slice(0, FIRST_ALIASES) as a}{@render aliasRow(a)}{/each}
			</ul>
			{#if actor.aliases.length > FIRST_ALIASES}
				<More total={actor.aliases.length} noun="names">
					<ul class="alias-list continued" aria-label="More names">
						{#each actor.aliases.slice(FIRST_ALIASES) as a}{@render aliasRow(a)}{/each}
					</ul>
				</More>
			{/if}
			<ul class="legend" aria-label="Key to the boxes">
				{#each NAME_SOURCES as n}
					<li><b>{n.code}</b> {sourceLabel(n.key).short}</li>
				{/each}
			</ul>
			<p class="key">A filled box means the source lists the name.</p>
		</section>

		{#if attribution.length > 0}
			<section aria-labelledby="attribution-heading">
				<h2 id="attribution-heading">Origin and Motivation</h2>
				<dl class="claims">
					{#each attribution as f (f.field)}
						<div>
							<dt>{f.label}</dt>
							<dd>
								{#if f.values.length > 0}{@render valueList(f.values, f.field, 'values')}{/if}
								{#each actor.conflicts.filter((c) => c.field === f.field) as c}
									<ConflictNote conflict={c} display={f.field === 'origin' ? countryName : undefined} />
								{/each}
							</dd>
						</div>
					{/each}
				</dl>
			</section>
		{/if}

		{#if hasTargets}
			<section aria-labelledby="targets-heading">
				<h2 id="targets-heading">Claimed targets (actor-level, per source)</h2>
				<p class="key lead">
					Sources give these countries and sectors for the actor as a whole. They do not say which
					report or campaign hit which target.
				</p>
				<dl class="claims">
					{#if targets.countries.length > 0}
						<div>
							<dt>Countries</dt>
							<dd>{@render valueList(targets.countries, 'origin', 'countries')}</dd>
						</div>
					{/if}
					{#if targets.sectors.length > 0}
						<div>
							<dt>Sectors</dt>
							<dd>{@render valueList(targets.sectors, 'sector', 'sectors')}</dd>
						</div>
					{/if}
				</dl>
			</section>
		{/if}

		{#if malware.length > 0}
			<section aria-labelledby="malware-heading">
				<h2 id="malware-heading">Malware and Tools</h2>
				<ul class="values">
					{@render valueItems(malware.slice(0, FIRST_CHIPS), 'malware')}
				</ul>
				{#if malware.length > FIRST_CHIPS}
					<More total={malware.length} noun="malware and tools">
						<ul class="values" aria-label="More malware and tools">
							{@render valueItems(malware.slice(FIRST_CHIPS), 'malware')}
						</ul>
					</More>
				{/if}
			</section>
		{/if}
	</aside>
</div>

<style>
	.actor-head {
		padding: 0.5rem 0 1.75rem;
		border-bottom: 1px solid var(--border);
	}

	.crumbs {
		margin: 0 0 1rem;
		font-size: 0.875rem;
	}

	.crumbs a::before {
		content: '← ';
	}

	h1 {
		margin-bottom: 0;
		overflow-wrap: anywhere;
	}

	.lede {
		max-width: 38rem;
		margin: 1rem 0 0;
		color: var(--text-muted);
		font-size: 1.1875rem;
		line-height: 1.5;
	}

	dt {
		margin: 0 0 0.125rem;
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	dd {
		margin: 0;
	}

	.facts {
		display: flex;
		flex-wrap: wrap;
		gap: 1.25rem 3rem;
		margin: 1.5rem 0 0;
	}

	.facts > div {
		min-width: 0;
	}

	.facts .num {
		color: var(--text);
		font-family: var(--font-data);
		font-size: 1.25rem;
		font-weight: 500;
		text-decoration-color: var(--border);
		text-decoration-thickness: 1px;
	}

	.facts a.num:hover {
		color: var(--accent);
		text-decoration-color: currentColor;
	}

	.facts .word {
		font-size: 1.0625rem;
		font-weight: 600;
		line-height: 1.9rem;
	}

	.meta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 2rem;
		margin: 1.25rem 0 0;
		font-size: 0.875rem;
	}

	.meta > div {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.5rem;
		min-width: 0;
	}

	.meta dt {
		margin: 0;
	}

	.meta .data {
		font-size: 0.8125rem;
	}

	.no-reports {
		max-width: 44rem;
		margin: 1.25rem 0 0;
		color: var(--text-muted);
	}

	.cols {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 2rem;
		padding: 2rem 0 4rem;
	}

	@media (min-width: 45rem) {
		.cols {
			grid-template-columns: minmax(0, 7fr) minmax(0, 5fr);
			gap: 3rem;
		}
	}

	@media (min-width: 45rem) {
		.cols.solo {
			grid-template-columns: minmax(0, 32rem);
		}
	}

	.main[hidden] {
		display: none;
	}

	.main,
	.side {
		min-width: 0;
	}

	section + section {
		margin-top: 2.25rem;
	}

	h2 {
		margin: 0 0 0.75rem;
		font-size: 1.5rem;
		line-height: 1.1;
	}

	h3 {
		margin: 1.5rem 0 0.5rem;
		font-size: 1.0625rem;
		line-height: 1.3;
	}

	.key {
		margin: 0.625rem 0 0;
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.key.lead {
		margin: 0 0 0.75rem;
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

	/* Ledger rows: an ink rule above, hairlines between. */
	.tech,
	.alias-list,
	.reports {
		margin: 0;
		padding: 0;
		list-style: none;
		border-top: 1px solid var(--text);
	}

	.continued,
	.more-list {
		border-top: 0;
	}

	.tech li {
		display: grid;
		grid-template-columns: 6rem minmax(0, 1fr) auto;
		gap: 0.75rem;
		align-items: baseline;
		padding: 0.5rem 0;
		border-bottom: 1px solid var(--border);
		font-size: 0.9375rem;
	}

	.tech .id {
		font-weight: 500;
	}

	.tech .n {
		color: var(--text-muted);
	}

	.tech .doc {
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		font-weight: 500;
		text-align: right;
		white-space: nowrap;
		overflow-wrap: normal;
	}

	.tech .doc.y {
		color: var(--text);
	}

	.alias-list li {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		gap: 1rem;
		align-items: baseline;
		padding: 0.4375rem 0;
		border-bottom: 1px solid var(--border);
	}

	.alias {
		min-width: 0;
		overflow-wrap: anywhere;
	}

	.srcs {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	.srcs .yes,
	.srcs .no {
		display: grid;
		place-items: center;
		width: 1.625rem;
		height: 1.25rem;
		border: 1px solid var(--text);
		border-radius: 2px;
		font-family: var(--font-data);
		font-size: 0.625rem;
		font-weight: 500;
		text-decoration: none;
	}

	.srcs .yes {
		background: var(--text);
		color: var(--bg);
	}

	.srcs .yes:hover {
		border-color: var(--accent);
		background: var(--accent);
		color: var(--ink-on-accent);
	}

	.srcs .no {
		border-color: var(--border);
	}

	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 1rem;
		margin: 0.75rem 0 0;
		padding: 0;
		list-style: none;
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.legend b {
		padding: 0 0.25rem;
		border: 1px solid var(--text);
		border-radius: 2px;
		background: var(--text);
		color: var(--bg);
		font-family: var(--font-data);
		font-size: 0.625rem;
		font-weight: 500;
	}

	.values,
	.ids {
		display: flex;
		flex-wrap: wrap;
		gap: 0.375rem 1.25rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.values li,
	.ids li {
		display: inline-flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.125rem 0.4375rem;
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

	.tag {
		display: inline-block;
		padding: 0 0.375rem;
		border: 1px solid var(--border);
		border-radius: 2px;
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		letter-spacing: 0.02em;
	}

	.tag.kev {
		border-color: var(--text);
		background: var(--text);
		color: var(--bg);
	}

	.report {
		display: grid;
		grid-template-columns: 6.5rem minmax(0, 1fr);
		gap: 1rem;
		min-width: 0;
		padding: 0.75rem 0;
		border-bottom: 1px solid var(--border);
	}

	.report p {
		margin: 0;
	}

	.report-date {
		padding-top: 0.1875rem;
		color: var(--text-muted);
	}

	.report-date .data {
		font-size: 0.75rem;
	}

	.report-body {
		min-width: 0;
	}

	.report-title {
		font-weight: 550;
		line-height: 1.4;
		overflow-wrap: anywhere;
	}

	.report-title a {
		color: var(--text);
		text-decoration: none;
	}

	.report-title a:hover {
		color: var(--accent);
		text-decoration: underline;
	}

	.report-meta,
	.report-links {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.125rem 0.875rem;
		margin-top: 0.25rem !important;
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.report-meta > *,
	.report-links > * {
		min-width: 0;
		overflow-wrap: anywhere;
	}

	.warn {
		color: var(--danger);
	}

	@media (max-width: 30rem) {
		.report {
			grid-template-columns: minmax(0, 1fr);
			gap: 0.125rem;
		}

		.tech li {
			grid-template-columns: 5rem minmax(0, 1fr) auto;
			gap: 0.5rem;
		}

		.facts {
			gap: 1rem 2rem;
		}
	}
</style>
