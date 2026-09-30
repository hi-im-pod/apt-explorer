<!--
	Page controls for the explore table. The same controls appear above and below
	the table; only the top copy announces the row range, so a screen reader hears
	it once. On a narrow screen the page numbers and the go-to-page field give way
	to Previous, "Page X of N" and Next.
-->
<script lang="ts">
	import { PAGE_SIZES, pageWindow, rangeLabel } from '$lib/paging';

	interface Props {
		position: 'top' | 'bottom';
		page: number;
		count: number;
		size: number;
		total: number;
		onpage: (page: number) => void;
		onsize: (size: number) => void;
	}

	let { position, page, count, size, total, onpage, onsize }: Props = $props();

	/** A number input binds to a number, or to null when it is empty or not a number. */
	let target = $state<number | null>(null);

	function submit(e: SubmitEvent) {
		e.preventDefault();
		if (target == null || !Number.isFinite(target)) return;
		const n = Math.trunc(target);
		target = null;
		onpage(Math.min(Math.max(1, n), count));
	}
</script>

<div class="bar" data-position={position}>
	{#if position === 'top'}
		<p class="range" aria-live="polite">{rangeLabel(page, size, total)}</p>
		<label class="size">
			Rows per page
			<select value={size} onchange={(e) => onsize(Number(e.currentTarget.value))}>
				{#each PAGE_SIZES as s (s)}<option value={s}>{s}</option>{/each}
			</select>
		</label>
	{/if}
	{#if count > 1}
		<nav class="pages" aria-label="Pages, {position} of table">
			<button type="button" class="step" disabled={page <= 1} onclick={() => onpage(page - 1)}>
				Previous
			</button>
			<ol class="numbers">
				{#each pageWindow(page, count) as item, i (item === 'gap' ? `gap${i}` : item)}
					<li>
						{#if item === 'gap'}
							<span class="gap" aria-hidden="true">…</span>
						{:else}
							<button
								type="button"
								class="num"
								aria-label="Page {item}"
								aria-current={item === page ? 'page' : undefined}
								onclick={() => item !== page && onpage(item)}
							>
								{item}
							</button>
						{/if}
					</li>
				{/each}
			</ol>
			<span class="position">Page {page} of {count}</span>
			<button type="button" class="step" disabled={page >= count} onclick={() => onpage(page + 1)}>
				Next
			</button>
			<form class="goto" novalidate onsubmit={submit}>
				<label>
					Go to page
					<input type="number" inputmode="numeric" min="1" max={count} bind:value={target} />
				</label>
				<button type="submit" class="step">Go</button>
			</form>
		</nav>
	{/if}
</div>

<style>
	.bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem 1rem;
		padding: 0.625rem 0;
	}

	.range {
		margin: 0;
		font-family: var(--font-data);
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	.size {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	select,
	input {
		min-height: 2.25rem;
		padding: 0.25rem 0.5rem;
		border: 1px solid var(--border);
		border-radius: 0.375rem;
		background: var(--surface);
		color: var(--text);
		font-family: var(--font-data);
		font-size: 0.8125rem;
	}

	input {
		width: 4.5rem;
	}

	select:focus-visible,
	input:focus-visible,
	button:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 2px;
	}

	.pages {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem;
		margin-left: auto;
	}

	.numbers {
		display: flex;
		gap: 0.25rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	button {
		min-height: 2.25rem;
		min-width: 2.25rem;
		padding: 0.25rem 0.625rem;
		border: 1px solid var(--border);
		border-radius: 0.375rem;
		background: transparent;
		color: var(--text);
		font-family: var(--font-data);
		font-size: 0.8125rem;
		cursor: pointer;
	}

	.step {
		font-family: var(--font-body);
		font-size: 0.875rem;
	}

	button:hover:not(:disabled) {
		border-color: var(--accent);
	}

	button:disabled {
		color: var(--text-muted);
		cursor: default;
		opacity: 0.55;
	}

	.num[aria-current='page'] {
		border-color: var(--accent);
		background: var(--accent-soft);
		font-weight: 600;
	}

	.gap {
		display: inline-block;
		min-width: 1.5rem;
		text-align: center;
		color: var(--text-muted);
	}

	.goto {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.goto label {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
	}

	.position {
		display: none;
		font-family: var(--font-data);
		font-size: 0.8125rem;
		color: var(--text-muted);
	}

	@media (max-width: 44.99rem) {
		.pages {
			width: 100%;
			justify-content: space-between;
			margin-left: 0;
		}

		.numbers,
		.goto {
			display: none;
		}

		.position {
			display: inline;
		}
	}
</style>
