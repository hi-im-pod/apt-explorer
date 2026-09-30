import { getActor, getGuesses, getResolution, getSources } from '$lib/data';
import type { PageLoad } from './$types';

// The group the grid on the home page is drawn for. Its ATT&CK ID is its file name.
const FEATURED_ACTOR = 'G0007';

export const load: PageLoad = async ({ fetch }) => {
	const [sources, actor, resolution, guesses] = await Promise.all([
		getSources(fetch),
		getActor(fetch, FEATURED_ACTOR),
		getResolution(fetch),
		getGuesses(fetch)
	]);
	return {
		sources,
		actor,
		// resolution.json is a few kilobytes, and the pipeline checks that its
		// actor count equals the length of actors/index.json, which is far larger.
		actorCount: resolution.stats.actor_count,
		guessCount: guesses.guesses.length
	};
};
