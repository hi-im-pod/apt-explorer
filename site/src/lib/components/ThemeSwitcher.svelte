<!--
	The theme control: a Light / Dark / APT strip. Closed, it is one button
	that shows the three names with the active one filled; opened, a menu of
	three radio items takes the strip's place, so picking is two steps
	and the keyboard and screen reader behaviour is the menu button pattern.

	It follows the WAI-ARIA menu button pattern. Opening the menu moves focus
	to the checked theme; arrow keys, Home and End move between themes;
	Enter or Space picks one; Escape closes the menu and returns focus to the
	button; Tab or a click outside closes it without moving focus back.
-->
<script lang="ts">
	import { tick } from 'svelte';
	import { THEMES, setTheme, theme, type Theme } from '$lib/theme';

	const NAMES: Record<Theme, string> = { light: 'Light', dark: 'Dark', apt: 'APT' };

	let open = $state(false);
	let root: HTMLDivElement;
	let trigger: HTMLButtonElement;
	const items: HTMLButtonElement[] = [];

	async function show() {
		open = true;
		await tick();
		items[Math.max(0, THEMES.indexOf($theme))]?.focus();
	}

	function hide(returnFocus: boolean) {
		open = false;
		if (returnFocus) trigger.focus();
	}

	function choose(t: Theme) {
		setTheme(t);
		hide(true);
	}

	function onTriggerKey(e: KeyboardEvent) {
		if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
			e.preventDefault();
			show();
		}
	}

	function onItemKey(e: KeyboardEvent, i: number) {
		const last = THEMES.length - 1;
		const next = i === last ? 0 : i + 1;
		const prev = i === 0 ? last : i - 1;
		const move: Record<string, number> = {
			ArrowDown: next,
			ArrowRight: next,
			ArrowUp: prev,
			ArrowLeft: prev,
			Home: 0,
			End: last
		};
		if (e.key in move) {
			e.preventDefault();
			items[move[e.key]]?.focus();
		} else if (e.key === 'Escape') {
			e.preventDefault();
			hide(true);
		} else if (e.key === 'Tab') {
			hide(false);
		}
	}

	function onWindowPointer(e: PointerEvent) {
		if (open && !root.contains(e.target as Node)) hide(false);
	}
</script>

<svelte:window onpointerdown={onWindowPointer} />

<div class="switcher" bind:this={root}>
	<button
		bind:this={trigger}
		type="button"
		class="trigger"
		aria-haspopup="menu"
		aria-expanded={open}
		aria-controls="theme-menu"
		onclick={() => (open ? hide(true) : show())}
		onkeydown={onTriggerKey}
	>
		<span class="visually-hidden">Theme</span>
		{#each THEMES as t (t)}
			<span class="seg" class:on={$theme === t} aria-hidden="true">{NAMES[t]}</span>
		{/each}
	</button>

	{#if open}
		<ul id="theme-menu" class="menu" role="menu" aria-orientation="horizontal" aria-label="Theme">
			{#each THEMES as t, i (t)}
				<li role="none">
					<button
						bind:this={items[i]}
						type="button"
						class="seg"
						role="menuitemradio"
						aria-checked={$theme === t}
						tabindex="-1"
						onclick={() => choose(t)}
						onkeydown={(e) => onItemKey(e, i)}
					>
						{NAMES[t]}
					</button>
				</li>
			{/each}
		</ul>
	{/if}
</div>

<style>
	.switcher {
		position: relative;
	}

	.trigger,
	.menu {
		display: flex;
		margin: 0;
		padding: 0;
		border: 1px solid var(--border);
		border-radius: 0.375rem;
		background: var(--bg);
		overflow: hidden;
		font-family: var(--font-data);
		font-size: 0.75rem;
		font-weight: 500;
		line-height: 1.25rem;
		list-style: none;
	}

	.trigger {
		color: var(--text-muted);
		cursor: pointer;
	}

	.trigger:hover {
		border-color: var(--accent);
	}

	/* The open menu sits exactly over the closed strip. */
	.menu {
		position: absolute;
		top: 0;
		right: 0;
		z-index: 10;
		border-color: var(--accent);
	}

	.seg {
		display: block;
		min-height: 1.75rem;
		padding: 0.25rem 0.625rem;
		border: 0;
		border-radius: 0;
		background: transparent;
		color: var(--text-muted);
		font: inherit;
		line-height: 1.25rem;
		white-space: nowrap;
		overflow-wrap: normal;
		cursor: pointer;
	}

	button.seg:hover {
		background: var(--accent-soft);
		color: var(--text);
	}

	.seg.on,
	.seg[aria-checked='true'] {
		background: var(--accent);
		color: var(--ink-on-accent);
	}

	.seg:focus-visible {
		outline-offset: -2px;
		border-radius: 0;
	}

	.trigger:focus-visible {
		outline-offset: 2px;
		border-radius: 0.375rem;
	}
</style>
