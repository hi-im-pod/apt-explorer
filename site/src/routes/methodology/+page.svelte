<script lang="ts">
	import { base } from '$app/paths';
	import { PUBLISH_POLICIES, sourceLabel } from '$lib/data/labels';
	import { formatCount } from '$lib/format';

	let { data } = $props();

	const stats = $derived(data.resolution.stats);
	const match = $derived(data.resolution.paper_match);
	const ambiguities = $derived(data.resolution.ambiguities);
	const unresolved = $derived(data.resolution.unresolved_names);

	// The published index is the list of actors that have a profile. A
	// candidate missing from it gets its ID as plain text, because a link
	// there would be a dead end.
	const names = $derived(new Map(data.actors.map((a) => [a.id, a.name])));

	const cards = $derived([
		{ label: 'Source records', value: stats.source_record_count },
		{ label: 'Actors', value: stats.actor_count },
		{ label: 'Merges', value: stats.merge_count },
		{ label: 'Evidence links', value: stats.evidence_edge_count },
		{ label: 'Ambiguous aliases', value: stats.ambiguity_count },
		{ label: 'Typed as software', value: stats.non_actor_name_count }
	]);

	// The three parts of the match add up to the total, so the bar and the
	// sentence cannot disagree. A build whose parts exceed the total shows a
	// remainder of zero, never a negative width.
	const unmatched = $derived(Math.max(0, match.names_total - match.resolved - match.typed_non_actor));
	const percent = (n: number) => (match.names_total > 0 ? (100 * n) / match.names_total : 0);

	const evidenceOnly = $derived(data.sources.filter((s) => s.publish === 'evidence-only'));
	const orklLinkOnly = $derived(data.sources.some((s) => s.name === 'orkl' && s.publish === 'link-only'));
	const stale = $derived(data.sources.filter((s) => s.stale));

	/** "A, B and C" */
	function joinNames(list: string[]): string {
		return list.length < 2 ? list.join('') : `${list.slice(0, -1).join(', ')} and ${list.at(-1)}`;
	}
</script>

<svelte:head>
	<title>Methodology · APT Explorer</title>
	<meta
		name="description"
		content="How APT Explorer merges actor records across sources, how well the merge matches the names in the CCS '25 data, and how it dates reports."
	/>
</svelte:head>

<div class="intro">
	<h1>Methodology</h1>
	<p class="lede">
		This page reports how the actor registry is built and how well it matches the actor names in the
		data released with the <a href="{base}/about/#paper">CCS '25 paper</a>. Every number comes from
		the data this build was made from, so it changes when the data does.
	</p>
</div>

<section id="registry" aria-labelledby="registry-heading">
	<h2 id="registry-heading">The Registry</h2>
	<p>
		The registry merges actor records from MITRE ATT&CK®, the MISP galaxy, ETDA's Threat Group Cards
		and Malpedia into one actor per group. It keeps the evidence for each merge, so the result can
		be checked.
	</p>
	<dl class="stats">
		{#each cards as c (c.label)}
			<div>
				<dt>{c.label}</dt>
				<dd class="data">{formatCount(c.value)}</dd>
			</div>
		{/each}
	</dl>
	<p class="section-note">
		Merges is the number of records folded into another record, which is source records minus
		actors. An evidence link is one shared name that joined two records. An ambiguous alias is a
		name that two ATT&CK groups both carry. Typed as software counts the names that belong to
		malware or a tool and to no actor.
	</p>
</section>

<section id="merging" aria-labelledby="merging-heading">
	<h2 id="merging-heading">How Records Are Merged</h2>
	<ol class="steps">
		<li>
			<strong>Names are normalized.</strong> The registry lowercases each name, folds full-width
			characters to plain ones, drops spaces and punctuation, and removes a trailing “Group” or
			“Team”. Digits stay, so APT28 and APT2 remain separate actors.
		</li>
		<li>
			<strong>Shared names make candidates.</strong> Two records are candidates for a merge when they
			share a normalized name or alias. Each shared name is kept as an evidence link, so every merge
			traces back to the names that caused it.
		</li>
		<li>
			<strong>Some names are left alone.</strong> A shared name never merges two groups that ATT&CK
			lists under different IDs. The name is recorded as an ambiguity and both groups stay separate.
		</li>
		<li>
			<strong>Software is not an actor.</strong> A name that matches a Malpedia malware family or an
			ATT&CK software entry, and no actor, is typed as malware or a tool and is not shown as an
			actor.
		</li>
	</ol>
</section>

<section id="paper-match" aria-labelledby="paper-match-heading">
	<h2 id="paper-match-heading">Match Against the Paper's Names</h2>
	{#if match.match_rate == null}
		<p>The comparison with the paper's actor names is not available for this build.</p>
	{:else}
		<p class="rate">
			<span class="data big">{(match.match_rate * 100).toFixed(1)}%</span>
			<span class="of">of the paper's names resolve to an actor</span>
		</p>
		<p>
			The CCS '25 dataset labels its reports with {formatCount(match.names_total)} actor names. The
			registry resolves {formatCount(match.resolved)} of them to an actor. Another {formatCount(
				match.typed_non_actor
			)} are typed as malware or a tool, so they are not actors at all. The remaining {formatCount(
				unmatched
			)} match neither.
		</p>
		<div
			class="bar"
			role="img"
			aria-label="{formatCount(match.resolved)} resolved, {formatCount(
				match.typed_non_actor
			)} typed as software, {formatCount(unmatched)} unmatched, out of {formatCount(
				match.names_total
			)} names"
		>
			<span class="seg resolved" style:width="{percent(match.resolved)}%"></span>
			<span class="seg software" style:width="{percent(match.typed_non_actor)}%"></span>
			<span class="seg unmatched" style:width="{percent(unmatched)}%"></span>
		</div>
		<ul class="key" aria-hidden="true">
			<li><span class="swatch resolved"></span>Resolved</li>
			<li><span class="swatch software"></span>Typed as software</li>
			<li><span class="swatch unmatched"></span>Unmatched</li>
		</ul>
		<p class="section-note">
			The match rate is the share of names that resolve to an actor. Software names do not raise it.
			It measures agreement between the paper's labels and the registry. It does not say how many of
			the resolved names are correct, because a resolved name is only as reliable as the aliases
			behind it.
		</p>
	{/if}
</section>

<section id="ambiguities" aria-labelledby="ambiguities-heading">
	<h2 id="ambiguities-heading">Ambiguous Aliases</h2>
	{#if ambiguities.length === 0}
		<p>No alias is ambiguous in this build.</p>
	{:else}
		<p>
			Each alias below is carried by more than one ATT&CK group. The registry cannot tell which group
			another source meant by it, so it does not merge the groups and does not use the alias to link
			a report to either one.
		</p>
		<table>
			<thead>
				<tr>
					<th scope="col">Alias</th>
					<th scope="col">Groups that carry it</th>
				</tr>
			</thead>
			<tbody>
				{#each ambiguities as a (a.alias)}
					<tr>
						<th scope="row" class="data">{a.alias}</th>
						<td>
							<ul class="candidates">
								{#each a.candidates as id (id)}
									<li>
										{#if names.has(id)}
											<a href="{base}/actors/{id}/">{names.get(id)}</a>
											<span class="data id">{id}</span>
										{:else}
											<span class="data id">{id}</span>
											<span class="no-profile">no profile</span>
										{/if}
									</li>
								{/each}
							</ul>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</section>

<section id="unresolved" aria-labelledby="unresolved-heading">
	<h2 id="unresolved-heading">Names That Did Not Resolve</h2>
	{#if unresolved.length === 0}
		<p>Every report actor name in this build resolved to an actor.</p>
	{:else}
		<p>
			These names appear in reports and resolve to no actor, most frequent first. A name typed as
			malware or a tool is software, not a missing actor. A name with no type may be an actor that
			none of the sources lists.
			<a href="{base}/guesses/">The Name Guesses page</a> gives a program's label for each one, with how
			often that method was right, and marks every label as pending confirmation.
		</p>
		<table>
			<thead>
				<tr>
					<th scope="col">Name</th>
					<th scope="col" class="num">Times seen</th>
					<th scope="col">Typed as</th>
				</tr>
			</thead>
			<tbody>
				{#each unresolved as n (n.name)}
					<tr>
						<th scope="row">{n.name}</th>
						<td class="num data">{formatCount(n.count)}</td>
						<td>{n.typed_as ?? 'not typed'}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</section>

<section id="report-dates" aria-labelledby="report-dates-heading">
	<h2 id="report-dates-heading">Report Dates</h2>
	<p>
		Each report has one date and a label for where the date came from. The first rule that gives a
		usable date wins.
	</p>
	<ol class="steps">
		<li>The Malpedia library date recorded for the report's URL (<code>malpedia-library</code>).</li>
		<li>
			The date at the start of the report's title (<code>title-date</code>). Some collections file a
			paper as "2014-11-14 - Title". The site uses that date when it is not later than the day ORKL
			added the report, and it removes the date from the title it shows.
		</li>
		<li>The file creation date stored in the report itself (<code>file-metadata</code>).</li>
		<li>
			The date ORKL added the report to its collection (<code>orkl-ingest</code>). This is when ORKL
			saw the report, not when it was published, so it can be later than the true date.
		</li>
	</ol>
	<p>
		A date before 1990 or a placeholder such as 0001-01-01 counts as missing, and the next rule
		applies. A report that passes none of the rules is undated. It is listed on its own and is
		never in a timeline or a trend.
	</p>
</section>

<section id="report-links" aria-labelledby="report-links-heading">
	<h2 id="report-links-heading">Report Links</h2>
	<p>
		A report can carry two addresses, and the site labels each one as the original publisher's page
		or as a copy. It decides from the address's host alone, never from the field the address was
		stored in, because a source can store a mirror where the publisher's link belongs.
		The <a href="{base}/about/#report-links">About page</a> lists every label.
	</p>
	<ol class="steps">
		<li>
			<strong>Known copy hosts are copies.</strong> An address on vx-underground.org,
			archive.orkl.eu, app.box.com, web.archive.org, archive.org, archive.ph, archive.is or
			archive.today is labelled as a mirror, an archive or a snapshot, and is never labelled as the
			original. A GitHub address counts as a mirror only under the CyberMonitor account, because the
			same host also serves publishers' own repositories.
		</li>
		<li>
			<strong>Hosts that serve other people's pages are not called the original.</strong> An
			address on a link shortener (t.co, bit.ly and similar), a reference site (Wikipedia, ETDA's
			Threat Group Cards or Malpedia), a file host (Google Drive, Dropbox, Mega, SlideShare, Scribd,
			Pastebin and similar) or a cache is labelled "Link, publisher not confirmed". The site cannot
			tell who wrote the page behind such an address.
		</li>
		<li>
			<strong>Any other web address is labelled as the original.</strong> This is a rule, not a
			check. The site does not confirm that the host is the publisher, so a copy on a host that is
			not on either list above would be labelled as an original.
		</li>
		<li>
			<strong>An unreadable address is dropped.</strong> A link that is not a web address cannot be
			followed, so the site does not show it.
		</li>
		<li>
			<strong>A failed link check moves a link back.</strong> The check covers one address per
			report, the one stored as its main link. If it failed, the panel marks that link as
			unreachable and lists the working links first. The link stays, because the check can be
			wrong.
		</li>
		<li>
			<strong>A missing original is stated, not filled in.</strong> When a report has only copies,
			the panel says that no original publisher link is known and names what the copies are. When
			it has only a link that is not confirmed, the panel says that no original is confirmed.
		</li>
	</ol>
	<p class="section-note">
		Many ORKL records give a mirror address and no publisher address. Finding the publisher for
		each of them needs another source, and the pipeline does not look one up yet.
	</p>
</section>

<section id="publishing" aria-labelledby="publishing-heading">
	<h2 id="publishing-heading">What Is Published</h2>
	<p>
		Each source has a publish value that limits what the site may show from it. The
		<a href="{base}/about/#publish-values">About page</a> gives the value and the licence for every
		source.
	</p>
	<h3><code>evidence-only</code></h3>
	<p>{PUBLISH_POLICIES['evidence-only']}</p>
	<p class="used">
		{#if evidenceOnly.length > 0}
			Used in this build by {joinNames(evidenceOnly.map((s) => sourceLabel(s.name).short))}.
		{:else}
			No source is evidence-only in this build.
		{/if}
	</p>
	{#if orklLinkOnly}
		<p>
			ORKL tags its reports with actor names. While ORKL is link-only, the site
			never shows those tags and never links a report to an actor on the strength of a tag alone. A
			report is linked to an actor only through Malpedia, ATT&CK references or the paper's data.
		</p>
		<p>
			The actors, CVEs and techniques listed for an ORKL report were added by this project, and
			the table can filter and search on them. Actors come from the sources named above, or from a
			title or text that names them. CVE and technique IDs are found by matching patterns in the
			report text. The link-only rule allows this because the project works out those
			identifiers itself.
		</p>
	{/if}
	<h3>Actors named in a title</h3>
	<p>
		The site keeps no post text from the Microsoft, Talos and ESET blogs, The DFIR Report or ORKL.
		It can still read the title it shows. When that title contains the name of an
		actor that has a page here, the report is linked to that actor, and the report panel lists
		it under "Named in the title", apart from the actors a source tags. The paper's own report
		titles are read the same way. ORKL's actor tags are still never shown or used for these links.
	</p>
	<p>
		The match is cautious. It reads whole words and uses only the names this site already
		publishes. It skips a name that belongs to two actors, a name that is also an ordinary word,
		and the names of malware that a title can mention without being about the actor. A missing
		link is a better error than a wrong one. A title is the publisher's own statement, but it is
		weaker than a tag, and it can name an actor in passing.
	</p>
	<h3>Actors named in the text</h3>
	<p>
		ORKL's report text is read once, when the report is fetched. The pipeline looks in it for the
		names of actors that have a page here and keeps only which actors it found, how often, and
		where the name first appears. The text itself is never stored or published. The report panel
		lists these actors under "Named in the text", apart from tagged actors and from those named in
		the title.
	</p>
	<p>
		This match is stricter than the title match, because a report mentions actors in passing. A
		name counts when it appears at least twice. A name of several words, or one with a digit, such
		as Fancy Bear or APT29, also counts when it appears once in the opening 300 words. It skips the
		same names as the title match. Only actors published when a report was read can be found in it,
		so an actor added later is found only in reports read after that.
	</p>
	<h3>Names a vendor post states</h3>
	<p>
		A vendor names an actor differently from everyone else, so a post titled with the vendor's
		label, such as Storm-3168, can miss the report that uses the actor's own name. The Microsoft,
		Talos and ESET blogs often say outright that two names are one actor, as in "JadePuffer, tracked by
		Microsoft as Storm-3168". The pipeline reads each post's text in memory for phrases that equate two
		names, such as "also known as", "tracked as" and "a.k.a.", then keeps the two names and drops the
		sentence. Phrases such as "overlaps with" and "similar to" are not read, because they say the two
		are different.
	</p>
	<p>
		A stated pair is used in two cases. When one name is an actor this site already publishes, the
		other becomes an alias of that actor. When neither name is known, the pair adds a new actor only
		if one name is a vendor cluster label such as Storm-3168 or UNC2452 and the name guesser calls
		both names an actor. The guesser alone is not enough, because it calls almost any capitalised
		name an actor, malware families included. A pair is never used to join two actors the sources
		keep apart, or to turn a malware family into an actor. The rule is provisional, and every alias
		it adds carries the blog's source badge.
	</p>
</section>

<section id="limitations" aria-labelledby="limitations-heading">
	<h2 id="limitations-heading">Known Limitations</h2>
	<ul class="limits">
		<li>
			Sources update on different schedules. The home page shows the last good fetch for each one,
			and a source that fails keeps its last good data until it recovers.
			{#if stale.length > 0}
				In this build, {joinNames(stale.map((s) => sourceLabel(s.name).short))}
				{stale.length === 1 ? 'is' : 'are'} stale.
			{/if}
		</li>
		<li>
			A report that no source connects to an actor appears on no profile, even when its text names
			one. Actor names found in report text are not extracted in this version.
		</li>
		<li>
			Two sources can disagree on a value such as origin. The profile shows every value with its
			source and does not pick one.
		</li>
	</ul>
</section>

<style>
	.intro,
	section > p,
	section > .steps,
	section > .limits {
		max-width: 68ch;
	}

	.lede {
		font-size: 1.1875rem;
		line-height: 1.5;
		color: var(--text-muted);
	}

	.section-note,
	.used {
		color: var(--text-muted);
		font-size: 0.9375rem;
	}

	/* The counts are a ledger of facts: a rule above, a hairline under each. */
	.stats {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		column-gap: 2rem;
		max-width: 52rem;
		margin: 1.25rem 0;
		border-top: 1px solid var(--text);
	}

	@media (min-width: 40rem) {
		.stats {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.stats > div {
		padding: 0.625rem 0;
		border-bottom: 1px solid var(--border);
	}

	/* The label sits above the number so a long label wraps instead of
	   pushing the ledger wider than its column. */
	dt {
		margin: 0 0 0.125rem;
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	dd {
		margin: 0;
	}

	.stats dd {
		font-size: 1.25rem;
		font-weight: 500;
		line-height: 1.3;
	}

	.steps,
	.limits {
		margin: 0 0 1rem;
		padding-left: 1.5rem;
	}

	.steps li,
	.limits li {
		margin-bottom: 0.625rem;
		padding-left: 0.25rem;
	}

	.rate {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.25rem 0.75rem;
	}

	.big {
		font-size: 2.25rem;
		font-weight: 600;
		line-height: 1;
	}

	.of {
		color: var(--text-muted);
	}

	/* Ink for what resolved, grey for software, an outline for what did not:
	   the parts read apart without a colour that means something else. */
	.bar {
		display: flex;
		max-width: 68ch;
		height: 0.75rem;
		overflow: hidden;
		border: 1px solid var(--border);
	}

	.seg {
		display: block;
		height: 100%;
	}

	.resolved {
		background: var(--text);
	}

	.software {
		background: var(--text-muted);
	}

	.unmatched {
		background: transparent;
	}

	.key {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 1.25rem;
		margin: 0.625rem 0 1rem;
		padding: 0;
		list-style: none;
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.swatch {
		display: inline-block;
		width: 0.625rem;
		height: 0.625rem;
		margin-right: 0.375rem;
		border-radius: 1px;
	}

	.swatch.unmatched {
		box-shadow: inset 0 0 0 1px var(--text-muted);
	}

	table {
		width: 100%;
		max-width: 68ch;
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
		/* An alias key can be one long unbroken string. */
		overflow-wrap: anywhere;
	}

	thead th {
		border-bottom-color: var(--text);
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		font-weight: 500;
	}

	tbody th {
		font-weight: 500;
	}

	.num {
		text-align: right;
		padding-right: 1rem;
	}

	.candidates {
		display: grid;
		gap: 0.25rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	.id,
	.no-profile {
		margin-left: 0.375rem;
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	code {
		color: var(--text);
	}
</style>
