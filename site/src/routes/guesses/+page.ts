import { getGuesses } from '$lib/data';
import type { PageLoad } from './$types';

// A universal load, like the Methodology page: the file holds a few hundred
// short rows at most, every visitor needs it whole, and inlining it keeps
// the prerendered page readable with scripts blocked.
export const load: PageLoad = async ({ fetch }) => {
	return { guesses: await getGuesses(fetch) };
};
