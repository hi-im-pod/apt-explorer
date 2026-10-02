<script lang="ts">
	import { base } from '$app/paths';
	import Profile from './Profile.svelte';

	let { data } = $props();
</script>

<!-- A profile writes its own head. The head of a stub is here because svelte:head cannot sit in a block. -->
<svelte:head>
	{#if data.stub}
		{#if data.stub.successor}
			<title>{data.stub.display_name} was merged · Actors · APT Explorer</title>
			<meta name="description" content="{data.stub.display_name} is now part of {data.stub.successor.display_name}." />
		{:else}
			<title>{data.stub.display_name} is no longer listed · Actors · APT Explorer</title>
			<meta name="description" content="{data.stub.display_name} is no longer listed on APT Explorer." />
		{/if}
		<!-- A stub is a forwarding note, not a page worth finding in a search. -->
		<meta name="robots" content="noindex" />
	{/if}
</svelte:head>

{#if data.stub}
	<!-- A slug that was merged into another actor. Nothing else on this page is about an actor. -->
	<header class="stub">
		<p class="crumbs"><a href="{base}/actors/">All actors</a></p>
		{#if data.stub.successor}
			<h1>{data.stub.display_name} was merged into {data.stub.successor.display_name}</h1>
			<p>
				The records tracked under this name were matched to {data.stub.successor.display_name} in a later
				build, and the two are now one profile.
			</p>
			<p class="go">
				<a href="{base}/actors/{data.stub.successor.slug}/">Go to the profile of {data.stub.successor.display_name}</a>
			</p>
		{:else}
			<h1>{data.stub.display_name} is no longer listed</h1>
			<p>
				The sources this site builds from no longer describe an actor under this name.
			</p>
			<p class="go"><a href="{base}/actors/">See all actors</a></p>
		{/if}
	</header>
{:else if data.actor}
	<Profile actor={data.actor} reports={data.reports} />
{/if}

<style>
	.stub {
		max-width: 40rem;
		padding-block: 0.5rem 3rem;
	}

	.crumbs {
		margin: 0 0 0.5rem;
		font-size: 0.875rem;
	}

	.crumbs a::before {
		content: '← ';
	}

	h1 {
		overflow-wrap: anywhere;
	}

	.go {
		margin-top: 1.5rem;
		font-size: 1.0625rem;
	}
</style>
