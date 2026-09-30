<!--
	The rest of a long list, behind a native <details>.

	The control opens without scripts, so the prerendered page still holds
	every item. It stays where it is when it opens and the rest appears below
	it, so nothing above it moves, and keyboard focus stays on it because it
	is never hidden.
-->
<script lang="ts">
	import type { Snippet } from 'svelte';
	import { formatCount } from '$lib/format';

	let { total, noun, children }: { total: number; noun: string; children: Snippet } = $props();
</script>

<details class="more">
	<summary>
		<span class="closed">Show all {formatCount(total)} {noun}</span>
		<span class="opened">Show fewer</span>
	</summary>
	<div class="rest">{@render children()}</div>
</details>

<style>
	.more {
		margin-top: 0.75rem;
	}

	summary {
		display: inline-flex;
		align-items: center;
		min-height: 2.25rem;
		padding: 0 0.875rem;
		border: 1px solid var(--border);
		border-radius: 0.375rem;
		background: var(--surface);
		color: var(--text);
		font-size: 0.875rem;
		font-weight: 550;
		cursor: pointer;
		list-style: none;
	}

	summary::-webkit-details-marker {
		display: none;
	}

	summary:hover {
		border-color: var(--accent);
		color: var(--accent);
	}

	.opened,
	.more[open] .closed {
		display: none;
	}

	.more[open] .opened {
		display: inline;
	}

	.rest {
		margin-top: 0.5rem;
	}
</style>
