<script lang="ts">
	import { base } from '$app/paths';
	import type { PublishPolicy } from '$lib/data';
	import { PUBLISH_POLICIES, sourceLabel } from '$lib/data/labels';
	import { formatCount, formatDate } from '$lib/format';
	import { LINK_KINDS } from '$lib/links';

	let { data } = $props();

	// License names, links and attribution text all come from sources.json,
	// which the pipeline's tests hold to SOURCES.md. Nothing here retypes
	// them, so a new copyright year or license reaches the page with the data.
	const attack = $derived(data.sources.find((s) => s.name === 'attack'));
	const paper = $derived(data.sources.find((s) => s.name === 'paper'));

	const DATA_LICENSE_URL = 'https://creativecommons.org/licenses/by-nc-sa/4.0/';
	const POLICIES: PublishPolicy[] = ['full', 'derived-only', 'link-only', 'evidence-only'];

	/** "A, B and C" */
	function joinNames(names: string[]): string {
		return names.length < 2 ? names.join('') : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`;
	}

	const usedBy = (p: PublishPolicy) =>
		joinNames(data.sources.filter((s) => s.publish === p).map((s) => sourceLabel(s.name).short));
</script>

<svelte:head>
	<title>About · APT Explorer</title>
	<meta
		name="description"
		content="What APT Explorer is, the paper it builds on, and the license and attribution for every source it uses."
	/>
</svelte:head>

<div class="intro">
	<h1>About APT Explorer</h1>
	<p class="lede">
		APT Explorer tracks advanced persistent threat (APT) actors, the reports written about them and
		current reporting trends. It is a personal, non-commercial research project built only from open
		sources.
	</p>
	<p>
		Different sources give the same actor different names: one vendor's APT28 is another's Fancy
		Bear, Sofacy or Sednit. The site merges actor records from MITRE ATT&CK®, the MISP galaxy, ETDA's
		Threat Group Cards and Malpedia, and records the evidence behind each merge. Where sources
		disagree, such as on an actor's origin, the site shows every value with its source. The
		<a href="{base}/methodology/">Methodology</a> page reports how well the merge works.
	</p>
	<p>
		Reports belong to their authors. The site publishes derived facts, metadata and links, and it
		never re-hosts a report's text or PDF.
	</p>
</div>

<section id="paper" aria-labelledby="paper-heading">
	<h2 id="paper-heading">Built on Yuldoshkhujaev et al. (CCS '25)</h2>
	<p>
		This project builds on Yuldoshkhujaev, Jeon, Kim, Nikiforakis and Koo,
		<cite>A Decade-long Landscape of Advanced Persistent Threats: Longitudinal Analysis and Global
			Trends</cite
		>, published at the 2025 ACM SIGSAC Conference on Computer and Communications Security (CCS
		'25). The preprint is on <a href="https://arxiv.org/abs/2509.07457">arXiv (2509.07457)</a>.
	</p>
	{#if paper}
		<p>
			The authors released their data as
			<a href="https://zenodo.org/records/16869733">Zenodo record 16869733</a>
			under <a href={paper.licence_url}>{paper.licence}</a>. The dataset covers reports from 2014 to 2023 and appears
			here as a separate, labeled layer. No view reproduces a figure from the paper.
		</p>
		<div class="attribution">
			<p class="label">Dataset attribution</p>
			<blockquote><p>{paper.attribution}</p></blockquote>
		</div>
	{/if}
</section>

<section id="related-work" aria-labelledby="related-work-heading">
	<h2 id="related-work-heading">Related Work: APT Map</h2>
	<p>
		<a href="https://lngt-apt-study-map.vercel.app/">APT Map</a> is an interactive map of
		hand-curated incident rows, built from the dataset released with the paper above. It shows
		incidents from the victim's side or the attacker's side and filters them by year, country and
		actor. Community additions are made by GitHub pull request.
	</p>
	<p>
		APT Explorer answers a different question. It is an explorer of actors and of the reports
		written about them, and its pipeline can be rebuilt from open sources. The two projects share a
		starting point, and the dataset credit belongs to the paper's authors.
	</p>
	<ul class="related">
		<li><a href="https://lngt-apt-study-map.vercel.app/">APT Map, the interactive site</a></li>
		<li><a href="https://github.com/SecAI-Lab/APTMap-backend">SecAI-Lab/APTMap-backend on GitHub</a></li>
		<li>
			<a href="https://github.com/SecAI-Lab/A-Decade-long-Landscape-of-Advanced-Persistent-Threats"
				>SecAI-Lab/A-Decade-long-Landscape-of-Advanced-Persistent-Threats on GitHub</a
			>
		</li>
	</ul>
</section>

<section id="sources" aria-labelledby="sources-heading">
	<h2 id="sources-heading">Sources and Licenses</h2>
	<p class="section-note">
		Each source's license decides what the site may publish from it. The project's SOURCES.md file
		quotes every license and records the decision.
	</p>
	<ul class="sources">
		{#each data.sources as s (s.name)}
			{@const label = sourceLabel(s.name)}
			<li id="source-{s.name}" class="source" class:stale={s.stale}>
				<div class="meta">
					<h3 id="h-{s.name}">{label.name}</h3>
					{#if label.role}<p class="role">{label.role}</p>{/if}
					<dl>
						<div>
							<dt>Publish</dt>
							<dd><a class="policy" href="#publish-{s.publish}">{s.publish}</a></dd>
						</div>
						<div>
							<dt>License</dt>
							<dd><a href={s.licence_url}>{s.licence}</a></dd>
						</div>
						<div>
							<dt>Last good fetch</dt>
							<dd>
								{#if s.last_success}<time datetime={s.last_success}>{formatDate(s.last_success)}</time
									>{:else}never{/if}
								{#if s.stale}<span class="stale-tag">Stale</span>{/if}
							</dd>
						</div>
						<div>
							<dt>Records</dt>
							<dd class="data">{formatCount(s.record_count)}</dd>
						</div>
					</dl>
				</div>
				<div class="attribution">
					<p class="label">Attribution</p>
					<blockquote><p>{s.attribution}</p></blockquote>
				</div>
			</li>
		{/each}
	</ul>
</section>

<section id="publish-values" aria-labelledby="publish-heading">
	<h2 id="publish-heading">What Each Publish Value Means</h2>
	<p class="section-note">
		A source's publish value limits what the site may show from it. It never reduces what the
		license requires: attribution, NonCommercial and ShareAlike terms apply in full.
	</p>
	<dl class="policies">
		{#each POLICIES as p (p)}
			<div id="publish-{p}">
				<dt><code>{p}</code></dt>
				<dd>
					<p>{PUBLISH_POLICIES[p]}</p>
					<p class="used">
						{#if usedBy(p)}Used by {usedBy(p)}.{:else}No source uses this value in this build.{/if}
					</p>
				</dd>
			</div>
		{/each}
	</dl>
</section>

<section id="report-links" aria-labelledby="report-links-heading">
	<h2 id="report-links-heading">Original, Archive and Mirror Links</h2>
	<p class="section-note">
		A report can have two links: the publisher's own page and a copy held by someone else. The
		site labels each link by where it goes, so a copy is never passed off as the original. The
		<a href="{base}/methodology/#report-links">Methodology</a> page explains how and where the
		label can be wrong.
	</p>
	<dl class="kinds">
		{#each LINK_KINDS as k (k.kind)}
			<div data-kind={k.kind}>
				<dt>{k.label}</dt>
				<dd>{k.explanation}</dd>
			</div>
		{/each}
	</dl>
	<p class="section-note">
		Some reports have no known original. Their records point only to a mirror or to a link whose
		publisher the site cannot confirm, and the panel says so. The site does not guess one.
	</p>
</section>

<section id="data-licence" aria-labelledby="licence-heading">
	<h2 id="licence-heading">Data License</h2>
	<p>
		The published data is offered under the
		<a href={DATA_LICENSE_URL}
			>Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License (CC BY-NC-SA
			4.0)</a
		>.
	</p>
	<p>
		It carries this license because it adapts two share-alike sources: values from ETDA's Threat
		Group Cards and from Malpedia are normalized and merged with the other sources. Anyone who
		reuses the data receives the same NonCommercial and ShareAlike terms and must credit the sources
		listed above.
	</p>
	<p>
		No additional terms apply to the data, and the license of the APT Explorer code does not cover
		it. The same notice ships with the data as <a href="{base}/data/NOTICE.md">NOTICE.md</a>.
	</p>
	{#if attack}
		<h3>MITRE ATT&CK</h3>
		<p>
			Values from MITRE ATT&CK stay under MITRE's license, which requires its copyright designation
			and license in every copy:
		</p>
		<blockquote class="notice"><p>{attack.attribution}</p></blockquote>
	{/if}
	<p class="section-note">
		APT Explorer is not affiliated with, sponsored by or endorsed by MITRE, CISA or the US Department
		of Homeland Security (DHS), and it does not use the CISA logo or the DHS seal.
	</p>
</section>

<style>
	.intro,
	section > p,
	.section-note {
		max-width: 68ch;
	}

	.lede {
		font-size: 1.1875rem;
		line-height: 1.5;
		color: var(--text-muted);
	}

	.section-note {
		color: var(--text-muted);
	}

	cite {
		font-style: italic;
	}

	/* Attribution text is quoted as given, so it gets a quiet rule rather
	   than body styling. */
	.attribution .label,
	dt {
		margin: 0 0 0.125rem;
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.75rem;
	}

	blockquote {
		padding: 0.125rem 0 0.125rem 1rem;
		border-left: 2px solid var(--text-muted);
		font-size: 0.9375rem;
	}

	blockquote p {
		margin: 0;
	}

	#paper .attribution {
		max-width: 68ch;
		margin-top: 1.25rem;
	}

	/* Each source is a ledger row: a rule above, the facts beside the quoted attribution. */
	.sources {
		margin: 1.5rem 0 0;
		padding: 0;
		border-top: 1px solid var(--text);
		list-style: none;
	}

	.source {
		display: grid;
		gap: 1rem 2rem;
		padding: 1.25rem 0;
		border-bottom: 1px solid var(--border);
	}

	@media (min-width: 56rem) {
		.source {
			grid-template-columns: minmax(16rem, 22rem) 1fr;
		}
	}

	.source h3 {
		margin: 0 0 0.25rem;
	}

	.role {
		margin: 0 0 0.75rem;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.source dl {
		display: grid;
		/* The first column holds the date, which needs the extra room at 375px. */
		grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
		gap: 0.625rem 1rem;
		margin: 0;
	}

	.source dd {
		margin: 0;
		font-size: 0.875rem;
	}

	.policy {
		display: inline-block;
		padding: 0 0.5rem;
		border: 1px solid var(--border);
		border-radius: 999px;
		font-family: var(--font-data);
		font-size: 0.75rem;
		text-decoration: none;
	}

	.policy:hover {
		border-color: var(--accent);
	}

	.stale-tag {
		display: inline-block;
		margin-left: 0.25rem;
		padding: 0 0.375rem;
		border: 1px solid var(--danger);
		border-radius: 0.25rem;
		color: var(--danger);
		font-family: var(--font-data);
		font-size: 0.6875rem;
	}

	.source.stale {
		box-shadow: inset 3px 0 0 var(--danger);
		padding-left: 1rem;
	}

	.source time {
		font-family: var(--font-data);
		font-size: 0.8125rem;
	}

	.source .attribution blockquote {
		color: var(--text);
	}

	.policies,
	.kinds {
		max-width: 68ch;
		margin: 1.25rem 0;
		border-top: 1px solid var(--text);
	}

	.policies > div,
	.kinds > div {
		padding: 0.75rem 0;
		border-bottom: 1px solid var(--border);
		scroll-margin-top: 1rem;
	}

	.policies > div:target {
		background: var(--accent-soft);
		box-shadow: inset 3px 0 0 var(--accent);
		padding-left: 0.875rem;
	}

	.policies dt code {
		font-size: 0.8125rem;
		color: var(--text);
	}

	.policies dd {
		margin: 0;
	}

	.policies dd p {
		margin: 0 0 0.375rem;
	}

	.policies .used {
		margin: 0;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.notice {
		max-width: 68ch;
		margin: 0 0 1.25rem;
	}

	.related {
		max-width: 68ch;
		margin: 0.75rem 0 0;
		padding-left: 1.25rem;
	}

	.related li {
		margin-bottom: 0.375rem;
		/* Repository names are long single words, so they must wrap at 375px. */
		overflow-wrap: anywhere;
	}

	.kinds dt {
		margin: 0 0 0.125rem;
		color: var(--text);
		font-family: var(--font-body, inherit);
		font-size: 0.9375rem;
		font-weight: 600;
	}

	.kinds dd {
		margin: 0;
		color: var(--text-muted);
		font-size: 0.9375rem;
	}
</style>
