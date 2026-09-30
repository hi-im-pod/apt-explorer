<!--
	The source behind one published value.

	The badge links to the source's entry on the About page, where its
	licence, publish value and attribution are, so every fact on the site is
	one click from the terms it was published under. The full name is in the
	title for a pointer hover; the visible text is the short form, because a
	row of badges must fit beside an alias at phone width.
-->
<script lang="ts">
	import { base } from '$app/paths';
	import type { SourceKey } from '$lib/data';
	import { sourceLabel } from '$lib/data/labels';

	interface Props {
		source: SourceKey;
		/** False where the same links would repeat on every row, such as a long list. */
		link?: boolean;
	}

	let { source, link = true }: Props = $props();

	const label = $derived(sourceLabel(source));
</script>

{#if link}
	<a class="badge" href="{base}/about/#source-{source}" title={label.name}>{label.short}</a>
{:else}
	<span class="badge" title={label.name}>{label.short}</span>
{/if}

<style>
	.badge {
		display: inline-block;
		padding: 0 0.4375rem;
		border: 1px solid var(--border);
		border-radius: 0.25rem;
		color: var(--text-muted);
		font-family: var(--font-data);
		font-size: 0.6875rem;
		line-height: 1.6;
		white-space: nowrap;
		text-decoration: none;
		vertical-align: 0.1em;
	}

	a.badge:hover {
		border-color: var(--accent);
		color: var(--text);
	}
</style>
