<script lang="ts">
	import '@fontsource-variable/mona-sans';
	import '@fontsource-variable/martian-mono';
	import '../app.css';
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { page } from '$app/state';
	import ThemeSwitcher from '$lib/components/ThemeSwitcher.svelte';
	import { formatDate } from '$lib/format';
	import { initTheme } from '$lib/theme';

	let { data, children } = $props();

	onMount(() => initTheme());

	const links = [
		{ path: '/explore/', label: 'Explore' },
		{ path: '/actors/', label: 'Actors' },
		{ path: '/trends/', label: 'Trends' },
		{ path: '/about/', label: 'About' }
	];

	// Compared by route ID rather than URL: during prerender `base` can be a
	// relative path, so a URL comparison would miss and the prerendered page
	// would lack the marker. An actor profile (/actors/[id]) marks Actors.
	const isCurrent = (path: string) => `${page.route.id ?? ''}/`.startsWith(path);
</script>

<a class="skip" href="#main">Skip to content</a>

<header class="site-header">
	<div class="bar">
		<a class="brand" href="{base}/">
			<svg class="mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false">
				<circle cx="16" cy="16" r="13.5" />
				<circle cx="16" cy="16" r="8.5" opacity="0.75" />
				<circle cx="16" cy="16" r="3.5" opacity="0.55" />
				<circle class="blip" cx="24" cy="8.5" r="3" />
			</svg>
			<span>APT Explorer</span>
		</a>
		<nav aria-label="Main">
			<ul>
				{#each links as link (link.path)}
					<li>
						<a href="{base}{link.path}" aria-current={isCurrent(link.path) ? 'page' : undefined}
							>{link.label}</a
						>
					</li>
				{/each}
			</ul>
		</nav>
		<div class="theme">
			<ThemeSwitcher />
		</div>
	</div>
</header>

<main id="main" class="page">
	{@render children()}
</main>

<footer class="site-footer">
	<div class="inner">
		{#if data.build}
			<p>
				Data built <time datetime={data.build.built_at}>{formatDate(data.build.built_at)}</time>.
				The data is offered under CC BY-NC-SA 4.0.
			</p>
		{/if}
		<p class="links">
			<a href="{base}/about/">Sources and licences</a>
			<a href="{base}/methodology/">Methodology</a>
		</p>
	</div>
</footer>

<style>
	.skip {
		position: absolute;
		left: 1rem;
		top: -3rem;
		z-index: 20;
		padding: 0.5rem 0.75rem;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: 0.375rem;
	}

	.skip:focus {
		top: 0.75rem;
	}

	.site-header {
		position: relative;
		/* A faint dot grid: the one decorative texture, kept to the header so
		   it never sits behind body text. */
		background-color: var(--bg);
		background-image: radial-gradient(var(--grid) 1.2px, transparent 1.4px);
		background-size: 14px 14px;
	}

	/* The three-colour hairline under the header. */
	.site-header::after {
		content: '';
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		height: 2px;
		background: linear-gradient(90deg, var(--rule-1), var(--rule-2), var(--rule-3));
	}

	.bar {
		display: grid;
		grid-template-columns: 1fr auto;
		grid-template-areas:
			'brand theme'
			'nav nav';
		align-items: center;
		gap: 0.75rem 1rem;
		max-width: 72rem;
		margin: 0 auto;
		padding: 0.875rem 16px 0.75rem;
	}

	.brand {
		grid-area: brand;
		display: inline-flex;
		align-items: center;
		gap: 0.625rem;
		justify-self: start;
		color: var(--text);
		font-family: var(--font-data);
		font-size: 0.9375rem;
		font-weight: 600;
		letter-spacing: 0.02em;
		text-decoration: none;
	}

	.mark {
		width: 1.75rem;
		height: 1.75rem;
		fill: none;
		stroke: var(--accent);
		stroke-width: 2.25;
	}

	.mark .blip {
		fill: var(--accent-2);
		stroke: none;
	}

	nav {
		grid-area: nav;
	}

	nav ul {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 1.25rem;
		margin: 0;
		padding: 0;
		list-style: none;
	}

	nav a {
		display: inline-block;
		padding: 0.25rem 0;
		color: var(--text-muted);
		font-weight: 550;
		text-decoration: none;
		border-bottom: 2px solid transparent;
	}

	nav a:hover {
		color: var(--text);
	}

	nav a[aria-current='page'] {
		color: var(--text);
		border-bottom-color: var(--accent);
	}

	.theme {
		grid-area: theme;
	}

	@media (min-width: 45rem) {
		.bar {
			grid-template-columns: auto 1fr auto;
			grid-template-areas: 'brand nav theme';
			gap: 1rem 2.5rem;
			padding: 1rem 24px;
		}
	}

	.page {
		display: block;
		flex: 1 0 auto;
		width: 100%;
		max-width: 72rem;
		margin: 0 auto;
		padding: 2rem 16px 4rem;
	}

	@media (min-width: 45rem) {
		.page {
			padding: 3rem 24px 5rem;
		}
	}

	.site-footer {
		border-top: 1px solid var(--border);
		color: var(--text-muted);
		font-size: 0.875rem;
	}

	.site-footer .inner {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		gap: 0.5rem 2rem;
		max-width: 72rem;
		margin: 0 auto;
		padding: 1.5rem 16px 2rem;
	}

	.site-footer p {
		margin: 0;
	}

	.site-footer .links {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 1.25rem;
	}

	/* Martian Mono runs larger than Mona Sans at the same size. */
	.site-footer time {
		font-family: var(--font-data);
		font-size: 0.82em;
	}

	@media (min-width: 45rem) {
		.site-footer .inner {
			padding-inline: 24px;
		}
	}
</style>
