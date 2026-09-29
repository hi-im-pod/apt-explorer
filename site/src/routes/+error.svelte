<script lang="ts">
	import { base } from '$app/paths';
	import { page } from '$app/state';

	const notFound = $derived(page.status === 404);
</script>

<svelte:head>
	<title>{notFound ? 'Not found' : 'Error'} · APT Explorer</title>
</svelte:head>

<div class="error">
	{#if notFound}
		<p class="code data" aria-hidden="true">404</p>
		<h1>Not found</h1>
		<p>
			Nothing is published at <code>{page.url.pathname}</code>. The link may be mistyped, or the
			page may have moved.
		</p>
	{:else}
		<p class="code data" aria-hidden="true">{page.status}</p>
		<h1>Something went wrong</h1>
		<p>This page could not be loaded. {page.error?.message ?? ''}</p>
	{/if}
	<p>Go to the <a href="{base}/">home page</a>, or find an actor in the <a href="{base}/actors/">actors index</a>.</p>
</div>

<style>
	.error {
		max-width: 40rem;
		padding-block: 1rem 3rem;
	}

	.code {
		margin: 0 0 0.5rem;
		color: var(--accent);
		font-size: 0.875rem;
		letter-spacing: 0.2em;
	}
</style>
