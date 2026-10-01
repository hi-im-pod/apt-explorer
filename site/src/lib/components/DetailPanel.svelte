<!--
	The details of one report or campaign, opened from the explore table.

	It is a non-modal dialog: the table stays usable beside it on a wide
	screen, so a visitor can move from row to row without closing it. That
	means the browser gives it no Escape handling and no focus handling, so
	both are done here: opening moves focus to the heading, Escape or the
	close button calls onclose, and the page returns focus to the row.

	Links are sorted by what they are, not by which field held them. The
	original publisher's page is one kind of link; an archive or a mirror is
	a copy. Both are shown wherever both exist, each with its own label and a
	plain note on the difference, because a mirror must never pass as the
	publisher. When the last link check found the original unreachable, the
	copy comes first and the panel says why. A dead link is never dropped.
	The classification lives in $lib/links.

	A link-only row (ORKL, whose terms are pending) takes only its title,
	date and links from the source. Its actors, CVEs and techniques are
	shown too, because the table filters and searches on them and a panel
	that hid them would disagree with the list that opened it. They are not
	ORKL's own data: the pipeline links actors through Malpedia, ATT&CK and
	the paper, and finds CVE and technique IDs by matching the report text.
	The publisher and the names that matched no actor stay hidden.

	Actors are shown in two groups. A tagged actor was named by a source's
	own data. An actor "named in the title" was found by matching the title
	against known aliases, for the vendor blogs that publish no tags. The two
	are kept apart so a title match never passes as a tag. The split comes
	from the table row, not the report's record, so nothing shifts when the
	record loads.

	The table row already holds the title, date, publisher, sources, actors,
	CVEs and techniques, so the panel shows them at once. The links and the
	names that matched no actor live only in the report's own record, which
	the page reads from its year shard. Those two parts show a loading note,
	then either the record or an error with a retry button.
-->
<script lang="ts">
	import { tick } from 'svelte';
	import { base } from '$app/paths';
	import type { Report } from '$lib/data/types';
	import type { ExploreRow } from '$lib/search';
	import { sourceLabel } from '$lib/data/labels';
	import { formatDate } from '$lib/format';
	import { describeLinks } from '$lib/links';

	interface Props {
		/** Whether the panel is open. */
		open: boolean;
		/** The row to show, or null when the URL names one that is not in the data. */
		row: ExploreRow | null;
		/** What the URL asked for, for the not-found message. */
		requested: { kind: 'report' | 'campaign'; id: string } | null;
		actorNames: ReadonlyMap<string, string>;
		kevCves: ReadonlySet<string>;
		/** The report's full record, once its shard has been read. */
		report: Report | null;
		/** Where reading the record stands. Only a report row has one. */
		status: 'loading' | 'error' | 'ready';
		onretry: () => void;
		onclose: () => void;
	}

	let { open, row, requested, actorNames, kevCves, report, status, onretry, onclose }: Props = $props();

	let dialog: HTMLDialogElement;
	let heading = $state<HTMLHeadingElement>();

	/** The report's links in the order a visitor should try them, with a note on what they are. */
	const linkInfo = $derived(report ? describeLinks(report) : null);

	/** ATT&CK's page for a technique: T1566.002 lives at /techniques/T1566/002/. */
	function techniqueUrl(id: string): string {
		return `https://attack.mitre.org/techniques/${id.replace('.', '/')}/`;
	}

	/** ATT&CK campaign IDs are C followed by four digits; other sources' IDs have no ATT&CK page. */
	const attackCampaign = $derived(
		row?.campaign?.source === 'attack' && /^C\d{4}$/.test(row.campaign.id) ? row.campaign.id : null
	);

	const kindLabel = $derived(
		(row?.kind ?? requested?.kind) === 'campaign' ? 'Campaign' : 'Report'
	);

	// Open and close the dialog with the URL, and move focus to the heading
	// whenever it opens or starts showing a different row.
	$effect(() => {
		if (!dialog) return;
		if (open && !dialog.open) dialog.show();
		if (!open && dialog.open) dialog.close();
	});

	$effect(() => {
		void row?.key;
		void requested?.id;
		if (!open) return;
		tick().then(() => heading?.focus());
	});

	function onkeydown(e: KeyboardEvent) {
		// Another control (the theme menu) may have used this Escape already.
		if (!open || e.key !== 'Escape' || e.defaultPrevented) return;
		e.preventDefault();
		onclose();
	}
</script>

<svelte:window {onkeydown} />

<dialog class="panel" bind:this={dialog} aria-labelledby="panel-title">
	{#if open}
		<div class="top">
			<p class="kind" class:campaign={kindLabel === 'Campaign'}>{kindLabel}</p>
			<button type="button" class="close" onclick={onclose}>
				<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
					<path d="M3.5 3.5l9 9m0-9l-9 9" />
				</svg>
				Close
			</button>
		</div>

		{#if !row}
			<h2 id="panel-title" tabindex="-1" bind:this={heading}>{kindLabel} not found</h2>
			<p>
				<code>{requested?.id}</code> is not in the current data. A later build may have removed it,
				or the link may be mistyped.
			</p>
		{:else if row.kind === 'report'}
			<h2 id="panel-title" tabindex="-1" bind:this={heading}>{row.title}</h2>
			<dl class="meta">
				<div>
					<dt>Published</dt>
					<dd>
						{#if row.date}<time datetime={row.date}>{formatDate(row.date)}</time
							>{:else}Undated{/if}
					</dd>
				</div>
				{#if !row.linkOnly}
					<div>
						<dt>Publisher</dt>
						<dd>{row.organisation ?? 'not reported'}</dd>
					</div>
				{/if}
				<div>
					<dt>{row.sources.length > 1 ? 'Sources' : 'Source'}</dt>
					<dd>{row.sources.map((s) => sourceLabel(s).name).join(', ')}</dd>
				</div>
			</dl>

			<section aria-labelledby="panel-links">
				<h3 id="panel-links">Links</h3>
				{#if status === 'loading'}
					<p class="wait" role="status">Loading the links for this report…</p>
				{:else if status === 'error'}
					<p class="warn" role="alert">
						The links for this report could not be loaded.
						<button type="button" class="retry" onclick={onretry}>Try again</button>
					</p>
				{:else if linkInfo}
					<p
						class="note"
						class:warn={linkInfo.situation !== 'both' || linkInfo.links.some((l) => l.unreachable)}
						data-situation={linkInfo.situation}
					>
						{linkInfo.note}
					</p>
					{#if linkInfo.links.length}
						<ul class="links" aria-labelledby="panel-links">
							{#each linkInfo.links as link (link.href)}
								<li data-kind={link.class.kind} data-role={link.role}>
									<a href={link.href} rel="noopener noreferrer" target="_blank">{link.class.label}</a>
									<span class="host">{link.class.host}</span>
									{#if link.unreachable}<span class="dead">Unreachable at last check</span>{/if}
									<span class="what">{link.class.explanation}</span>
								</li>
							{/each}
						</ul>
					{/if}
					<p class="policy">
						<a href="{base}/methodology/#report-links"
							>How the site tells originals, archives and mirrors apart</a
						>
					</p>
				{/if}
			</section>

			{#snippet actorChip(id: string)}
				<li>
					{#if actorNames.has(id)}
						<a href="{base}/actors/{id}/">{actorNames.get(id)}</a>
					{:else}
						{id}
					{/if}
				</li>
			{/snippet}
			{@const tagged = row.actors.filter((id) => !row.actorsFromTitle.includes(id))}
			{#if tagged.length}
				<section aria-labelledby="panel-actors">
					<h3 id="panel-actors">Actors</h3>
					<ul class="chips">
						{#each tagged as id (id)}{@render actorChip(id)}{/each}
					</ul>
				</section>
			{/if}
			{#if row.actorsFromTitle.length}
				<section aria-labelledby="panel-titled">
					<h3 id="panel-titled">Named in the title</h3>
					<ul class="chips">
						{#each row.actorsFromTitle as id (id)}{@render actorChip(id)}{/each}
					</ul>
					<p class="hint">
						Found by matching the title against known actor names. The publisher's own tags
						did not confirm these.
					</p>
				</section>
			{/if}
			{#if !row.linkOnly && report && report.actor_names_unresolved.length}
				<section aria-labelledby="panel-unresolved">
					<h3 id="panel-unresolved">Names not matched to an actor</h3>
					<ul class="chips plain">
						{#each report.actor_names_unresolved as name (name)}<li>{name}</li>{/each}
					</ul>
				</section>
			{/if}
			{#if row.cves.length}
				<section aria-labelledby="panel-cves">
					<h3 id="panel-cves">CVEs</h3>
					<ul class="ids">
						{#each row.cves as cve (cve)}
							<li>
								<span class="data">{cve}</span>
								{#if kevCves.has(cve)}<span class="kev">In CISA KEV</span>{/if}
							</li>
						{/each}
					</ul>
				</section>
			{/if}
			{#if row.techniques.length}
				<section aria-labelledby="panel-techniques">
					<h3 id="panel-techniques">Techniques</h3>
					<ul class="ids">
						{#each row.techniques as t (t)}
							<li><a class="data" href={techniqueUrl(t)} rel="noopener noreferrer">{t}</a></li>
						{/each}
					</ul>
				</section>
			{/if}
			{#if row.linkOnly}
				<p class="policy">
					{sourceLabel('orkl').name} is a link-only source while its terms are confirmed, so it
					supplies only the report's title, date and links. The actors, CVEs and techniques above
					were added by this project. Actors come from Malpedia, MITRE ATT&CK and the paper, never
					from ORKL's tags or titles, and CVE and technique IDs are matched in the report text.
					<a href="{base}/about/#publish-link-only">What link-only means</a>
				</p>
			{/if}
		{:else if row.campaign}
			{@const c = row.campaign}
			<h2 id="panel-title" tabindex="-1" bind:this={heading}>{c.name}</h2>
			<dl class="meta">
				<div>
					<dt>Active</dt>
					<dd>
						{#if c.first_seen}<time datetime={c.first_seen}>{formatDate(c.first_seen)}</time
							>{:else}Start not reported{/if}
						{#if c.last_seen}
							to <time datetime={c.last_seen}>{formatDate(c.last_seen)}</time>
						{:else}
							to an end not reported
						{/if}
					</dd>
				</div>
				<div>
					<dt>Source</dt>
					<dd>{sourceLabel(c.source).name}</dd>
				</div>
			</dl>
			{#if attackCampaign}
				<p>
					<a href="https://attack.mitre.org/campaigns/{attackCampaign}/" rel="noopener noreferrer"
						>{attackCampaign} on MITRE ATT&CK</a
					>
				</p>
			{/if}
			{#if c.actors.length}
				<section aria-labelledby="panel-actors">
					<h3 id="panel-actors">Actors</h3>
					<ul class="chips">
						{#each c.actors as id (id)}
							<li>
								{#if actorNames.has(id)}
									<a href="{base}/actors/{id}/">{actorNames.get(id)}</a>
								{:else}
									{id}
								{/if}
							</li>
						{/each}
					</ul>
				</section>
			{/if}
			{#if c.techniques.length}
				<section aria-labelledby="panel-techniques">
					<h3 id="panel-techniques">Techniques</h3>
					<ul class="ids">
						{#each c.techniques as t (t)}
							<li><a class="data" href={techniqueUrl(t)} rel="noopener noreferrer">{t}</a></li>
						{/each}
					</ul>
				</section>
			{/if}
		{/if}
	{/if}
</dialog>

<style>
	/* A sheet fixed to the right edge on a wide screen, and the whole screen
	   on a narrow one. The dialog's user-agent box is reset first. */
	.panel {
		position: fixed;
		inset: 0 0 0 auto;
		z-index: 30;
		width: min(32rem, 100%);
		max-width: 100%;
		height: 100%;
		max-height: none;
		margin: 0;
		padding: 1rem 16px 3rem;
		overflow-y: auto;
		overscroll-behavior: contain;
		background: var(--surface);
		color: var(--text);
		border: 0;
		/* The same 3px accent bar as the selected row it belongs to. */
		border-left: 3px solid var(--accent);
		box-shadow: -1.5rem 0 3rem -1.5rem rgb(0 0 0 / 0.35);
	}

	@media (min-width: 45rem) {
		.panel {
			padding: 1.25rem 1.75rem 3rem;
		}
	}

	.top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 0.75rem;
	}

	.kind {
		margin: 0;
		color: var(--accent);
		font-family: var(--font-data);
		font-size: 0.75rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}

	/* Teal means campaign, here as in the table's tag. */
	.kind.campaign {
		color: var(--accent-2);
	}

	.close {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		min-height: 2.25rem;
		padding: 0.375rem 0.75rem;
		background: transparent;
		border: 1px solid var(--border);
		border-radius: 0.375rem;
		color: var(--text);
		font: inherit;
		font-size: 0.875rem;
		cursor: pointer;
	}

	.close:hover {
		border-color: var(--accent);
	}

	.close:focus-visible,
	.retry:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 2px;
	}

	.close svg {
		width: 0.875rem;
		height: 0.875rem;
		stroke: currentColor;
		stroke-width: 1.75;
		stroke-linecap: round;
		fill: none;
	}

	h2 {
		margin: 0 0 1rem;
		font-size: 1.375rem;
		line-height: 1.2;
	}

	/* The heading takes focus only so a screen reader starts reading at the
	   title. It is not a control, so it gets no focus ring. */
	h2:focus {
		outline: none;
	}

	h3 {
		margin: 1.5rem 0 0.5rem;
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		font-weight: 500;
		letter-spacing: 0.06em;
		text-transform: uppercase;
	}

	.meta {
		display: grid;
		gap: 0.375rem;
		margin: 0;
	}

	.meta div {
		display: grid;
		grid-template-columns: 6.5rem minmax(0, 1fr);
		gap: 0.75rem;
	}

	.meta dt {
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.meta dd {
		margin: 0;
	}

	.wait {
		margin: 0;
		color: var(--text-muted);
		font-size: 0.9375rem;
	}

	.retry {
		margin-left: 0.5rem;
		padding: 0.125rem 0.75rem;
		background: transparent;
		border: 1px solid var(--border);
		border-radius: 0.375rem;
		color: var(--text);
		font: inherit;
		font-size: 0.875rem;
		cursor: pointer;
	}

	.retry:hover {
		border-color: var(--accent);
	}

	.warn {
		padding: 0.5rem 0.75rem;
		border-left: 3px solid var(--danger);
		background: var(--bg);
		font-size: 0.9375rem;
	}

	.note {
		margin: 0 0 0.75rem;
		padding: 0.5rem 0.75rem;
		border-left: 3px solid var(--accent-2);
		background: var(--bg);
		font-size: 0.9375rem;
	}

	/* A missing original, or a dead one, is worth noticing; a plain copy is not an error. */
	.note.warn {
		border-left-color: var(--danger);
	}

	.links,
	.chips,
	.ids {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.links {
		flex-direction: column;
	}

	.links li {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.625rem;
	}

	.links a {
		font-weight: 600;
	}

	.links li {
		padding-bottom: 0.5rem;
	}

	.what {
		flex-basis: 100%;
		color: var(--text-muted);
		font-size: 0.8125rem;
		line-height: 1.4;
	}

	.dead {
		padding: 0 0.375rem;
		border: 1px solid var(--danger);
		border-radius: 0.25rem;
		color: var(--danger);
		font-size: 0.6875rem;
	}

	.host {
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.75rem;
	}

	.chips li {
		padding: 0.125rem 0.625rem;
		border-radius: 999px;
		background: var(--accent-soft);
	}

	.hint {
		margin: 0.5rem 0 0;
		color: var(--text-muted);
		font-size: 0.8125rem;
		line-height: 1.4;
	}

	.chips.plain li {
		background: transparent;
		border: 1px dashed var(--border);
	}

	.ids li {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.0625rem 0.5rem;
		border: 1px solid var(--border);
		border-radius: 0.25rem;
		font-size: 0.8125rem;
	}

	.kev {
		padding: 0 0.375rem;
		border: 1px solid var(--danger);
		border-radius: 0.25rem;
		color: var(--danger);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		letter-spacing: 0.04em;
	}

	.policy {
		margin-top: 1.5rem;
		color: var(--text-muted);
		font-size: 0.9375rem;
	}
</style>
