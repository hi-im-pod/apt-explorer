<!--
	The theme menu: a button that opens a menu of three radio items.

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
		const move: Record<string, number> = {
			ArrowDown: i === last ? 0 : i + 1,
			ArrowUp: i === 0 ? last : i - 1,
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
		<span class="swatch" aria-hidden="true"></span>
		<span>Theme</span>
	</button>

	{#if open}
		<ul id="theme-menu" class="menu" role="menu" aria-label="Theme">
			{#each THEMES as t, i (t)}
				<li role="none">
					<button
						bind:this={items[i]}
						type="button"
						role="menuitemradio"
						aria-checked={$theme === t}
						tabindex="-1"
						onclick={() => choose(t)}
						onkeydown={(e) => onItemKey(e, i)}
					>
						<span class="check" aria-hidden="true"></span>
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

	.trigger {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
		min-height: 2.25rem;
		padding: 0.25rem 0.75rem;
		border: 1px solid var(--border);
		border-radius: 999px;
		background: var(--surface);
		color: var(--text);
		font: inherit;
		font-size: 0.875rem;
		cursor: pointer;
	}

	.trigger:hover {
		border-color: var(--accent);
	}

	/* Shows the active theme's two accents, so the button previews it. */
	.swatch {
		width: 0.875rem;
		height: 0.875rem;
		border-radius: 50%;
		background: linear-gradient(135deg, var(--accent) 50%, var(--accent-2) 50%);
		box-shadow: 0 0 0 1px var(--border);
	}

	.menu {
		position: absolute;
		top: calc(100% + 0.375rem);
		right: 0;
		z-index: 10;
		min-width: 9.5rem;
		margin: 0;
		padding: 0.25rem;
		list-style: none;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 0.625rem;
		box-shadow: 0 0.5rem 1.5rem color-mix(in srgb, var(--text) 14%, transparent);
	}

	[role='menuitemradio'] {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		width: 100%;
		padding: 0.5rem 0.75rem;
		border: 0;
		border-radius: 0.4rem;
		background: transparent;
		color: var(--text);
		font: inherit;
		font-size: 0.9375rem;
		text-align: left;
		cursor: pointer;
	}

	[role='menuitemradio']:hover,
	[role='menuitemradio']:focus-visible {
		background: var(--accent-soft);
		outline-offset: -2px;
	}

	.check {
		width: 0.625rem;
		height: 0.625rem;
		border-radius: 50%;
		border: 1.5px solid var(--text-muted);
	}

	[aria-checked='true'] .check {
		border-color: var(--accent);
		background: var(--accent);
	}
</style>
