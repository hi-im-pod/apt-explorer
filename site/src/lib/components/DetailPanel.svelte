<!--
	The details of one report or campaign, opened from the explore table.

	It is a non-modal dialog: the table stays usable beside it on a wide
	screen, so a visitor can move from row to row without closing it. That
	means the browser gives it no Escape handling and no focus handling, so
	both are done here: opening moves focus to the heading, Escape or the
	close button calls onclose, and the page returns focus to the row.

	Link order follows the link check. The original comes first; when the
	last check found it unreachable, the archive copy comes first and the
	panel says why. A dead link is never dropped.

	A link-only row (ORKL, whose terms are pending) shows only its title,
	date and links. Its archive link is ORKL's own copy, offered only when
	the original is unreachable or missing.
-->
<script lang="ts">
	import { tick } from 'svelte';
	import { base } from '$app/paths';
	import type { ExploreRow } from '$lib/search';
	import { sourceLabel } from '$lib/data/labels';
	import { formatDate } from '$lib/format';

	interface Props {
		/** Whether the panel is open. */
		open: boolean;
		/** The row to show, or null when the URL names one that is not in the data. */
		row: ExploreRow | null;
		/** What the URL asked for, for the not-found message. */
		requested: { kind: 'report' | 'campaign'; id: string } | null;
		actorNames: ReadonlyMap<string, string>;
		kevCves: ReadonlySet<string>;
		onclose: () => void;
	}

	let { open, row, requested, actorNames, kevCves, onclose }: Props = $props();

	let dialog: HTMLDialogElement;
	let heading = $state<HTMLHeadingElement>();

	interface PanelLink {
		kind: 'original' | 'archive';
		href: string;
	}

	/** The report's links in the order a visitor should try them. */
	const links = $derived.by((): PanelLink[] => {
		const r = row?.report;
		if (!r) return [];
		const original: PanelLink | null = r.url ? { kind: 'original', href: r.url } : null;
		const archive: PanelLink | null = r.archive_url ? { kind: 'archive', href: r.archive_url } : null;
		const dead = r.url_ok === false;
		if (row?.linkOnly) {
			// ORKL's archive copy stands in only when the original cannot.
			if (original && !dead) return [original];
			return [archive, original].filter((l): l is PanelLink => l != null);
		}
		const ordered = dead ? [archive, original] : [original, archive];
		return ordered.filter((l): l is PanelLink => l != null);
	});

	const unreachable = $derived(row?.report?.url != null && row.report.url_ok === false);
	const noOriginal = $derived(row?.report != null && row.report.url == null);

	/** "harborcert.example", shown beside a link so the visitor knows where it goes. */
	function host(href: string): string {
		try {
			return new URL(href).hostname.replace(/^www\./, '');
		} catch {
			return '';
		}
	}

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
			<p class="kind">{kindLabel}</p>
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
		{:else if row.kind === 'report' && row.report}
			{@const r = row.report}
			<h2 id="panel-title" tabindex="-1" bind:this={heading}>{r.title}</h2>
			<dl class="meta">
				<div>
					<dt>Published</dt>
					<dd>
						{#if r.published}<time datetime={r.published}>{formatDate(r.published)}</time
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
				{#if unreachable}
					<p class="warn">
						The original link was unreachable at the last link check.
						{#if links[0]?.kind === 'archive'}The archive copy is listed first.{/if}
					</p>
				{:else if noOriginal}
					<p class="warn">
						This report has no original link.
						{#if links.length}The archive copy is listed instead.{/if}
					</p>
				{/if}
				{#if links.length}
					<ul class="links" aria-labelledby="panel-links">
						{#each links as link (link.kind)}
							<li>
								<a href={link.href} rel="noopener noreferrer" target="_blank"
									>{link.kind === 'original' ? 'Original report' : 'Archive copy'}</a
								>
								<span class="host">{host(link.href)}</span>
							</li>
						{/each}
					</ul>
				{:else}
					<p>No link is recorded for this report.</p>
				{/if}
			</section>

			{#if row.linkOnly}
				<p class="policy">
					{sourceLabel('orkl').name} is a link-only source while its terms are confirmed, so this panel
					shows only the report's title, date and links.
					<a href="{base}/about/#publish-link-only">What link-only means</a>
				</p>
			{:else}
				{#if r.actors.length}
					<section aria-labelledby="panel-actors">
						<h3 id="panel-actors">Actors</h3>
						<ul class="chips">
							{#each r.actors as id (id)}
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
				{#if row.unresolved.length}
					<section aria-labelledby="panel-unresolved">
						<h3 id="panel-unresolved">Names not matched to an actor</h3>
						<ul class="chips plain">
							{#each row.unresolved as name (name)}<li>{name}</li>{/each}
						</ul>
					</section>
				{/if}
				{#if r.cves.length}
					<section aria-labelledby="panel-cves">
						<h3 id="panel-cves">CVEs</h3>
						<ul class="ids">
							{#each r.cves as cve (cve)}
								<li>
									<span class="data">{cve}</span>
									{#if kevCves.has(cve)}<span class="kev">In CISA KEV</span>{/if}
								</li>
							{/each}
						</ul>
					</section>
				{/if}
				{#if r.techniques.length}
					<section aria-labelledby="panel-techniques">
						<h3 id="panel-techniques">Techniques</h3>
						<ul class="ids">
							{#each r.techniques as t (t)}
								<li><a class="data" href={techniqueUrl(t)} rel="noopener noreferrer">{t}</a></li>
							{/each}
						</ul>
					</section>
				{/if}
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
		border-left: 1px solid var(--border);
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

	.close {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.375rem 0.75rem;
		background: transparent;
		border: 1px solid var(--border);
		border-radius: 999px;
		color: var(--text);
		font: inherit;
		font-size: 0.875rem;
		cursor: pointer;
	}

	.close:hover {
		border-color: var(--accent);
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

	.warn {
		padding: 0.5rem 0.75rem;
		border-left: 3px solid var(--danger);
		background: var(--bg);
		font-size: 0.9375rem;
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

	.chips.plain li {
		background: transparent;
		border: 1px dashed var(--border);
	}

	.ids li {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
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
