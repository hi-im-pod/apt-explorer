<!--
	A field where the published sources disagree.

	The site never picks a winner: the note names every source and the value
	each one gives, and says that none was chosen. Sources that agree with
	each other are grouped, so three sources over two values read as one
	disagreement, not three.
-->
<script lang="ts">
	import type { Conflict } from '$lib/data';
	import SourceBadge from './SourceBadge.svelte';

	interface Props {
		conflict: Conflict;
		/** How to print a value, such as a country name for an ISO code. */
		display?: (value: string) => string;
	}

	let { conflict, display = (v: string) => v }: Props = $props();

	const groups = $derived.by(() => {
		const byValue = new Map<string, string[]>();
		for (const { value, source } of conflict.values) {
			const sources = byValue.get(value) ?? [];
			if (!sources.includes(source)) sources.push(source);
			byValue.set(value, sources);
		}
		return [...byValue].map(([value, sources]) => ({ value, sources }));
	});
</script>

<div class="conflict" role="note" aria-label="Sources disagree on {conflict.field}">
	<p>
		<strong>The sources disagree on {conflict.field}.</strong>
		{#each groups as g, i (g.value)}
			<span class="claim"
				>{#each g.sources as s, j (s)}{#if j > 0}{j === g.sources.length - 1 ? ' and ' : ', '}{/if}<SourceBadge
						source={s}
					/>{/each}
				{g.sources.length > 1 ? 'give' : 'gives'} <span class="value">{display(g.value)}</span></span
			>{i < groups.length - 1 ? ';' : '.'}
		{/each}
	</p>
</div>

<style>
	.conflict {
		max-width: 68ch;
		margin: 0.5rem 0 0;
		padding: 0.25rem 0 0.25rem 0.875rem;
		border-left: 3px solid var(--accent-2);
		font-size: 0.9375rem;
	}

	.conflict p {
		margin: 0;
	}

	.value {
		font-weight: 600;
	}
</style>
