<!--
	A field where the published sources disagree.

	The site never picks a winner: the note names every source and the value
	each one gives, and says that none was chosen. Sources that agree with
	each other are grouped, so three sources over two values read as one
	disagreement, not three. Each group also names the records that gave the
	value, because one actor can carry two groups that share a name. The
	actor's own name is left out of that list, since it adds nothing.
-->
<script lang="ts">
	import type { Conflict } from '$lib/data';
	import SourceBadge from './SourceBadge.svelte';

	interface Props {
		conflict: Conflict;
		/** How to print a value, such as a country name for an ISO code. */
		display?: (value: string) => string;
		/** The actor's name, left out of the list of record names. */
		actorName?: string;
	}

	const SHOWN_NAMES = 3;

	let { conflict, display = (v: string) => v, actorName = '' }: Props = $props();

	const groups = $derived.by(() => {
		const byValue = new Map<string, { sources: string[]; names: string[] }>();
		for (const { value, source, name } of conflict.values) {
			const group = byValue.get(value) ?? { sources: [], names: [] };
			if (!group.sources.includes(source)) group.sources.push(source);
			if (!group.names.some((n) => n.toLowerCase() === name.toLowerCase())) group.names.push(name);
			byValue.set(value, group);
		}
		return [...byValue].map(([value, { sources, names }]) => ({
			value,
			sources,
			names: names.length === 1 && names[0].toLowerCase() === actorName.toLowerCase() ? [] : names
		}));
	});

	/** "A, B and C", or "A, B, C and 2 more" past three names. */
	function nameList(names: string[]): string {
		const shown = names.slice(0, SHOWN_NAMES);
		const rest = names.length - shown.length;
		if (rest > 0) shown.push(`${rest} more`);
		return shown.length === 1 ? shown[0] : `${shown.slice(0, -1).join(', ')} and ${shown[shown.length - 1]}`;
	}
</script>

<div class="conflict" role="note" aria-label="Sources disagree on {conflict.field}">
	<p>
		<strong>The sources disagree on {conflict.field}.</strong>
		{#each groups as g, i (g.value)}
			<span class="claim"
				>{#each g.sources as s, j (s)}{#if j > 0}{j === g.sources.length - 1 ? ' and ' : ', '}{/if}<SourceBadge
						source={s}
					/>{/each}
				{g.sources.length > 1 ? 'give' : 'gives'} <span class="value">{display(g.value)}</span
				>{#if g.names.length > 0}{' '}<span class="names">({nameList(g.names)})</span>{/if}</span
			>{i < groups.length - 1 ? ';' : '.'}{' '}
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

	.names {
		color: var(--text-muted);
	}
</style>
