import { getGuesses, getTerms } from '$lib/data';
import type { PageLoad } from './$types';

// A universal load, like the Methodology page: the file holds a few hundred
// short rows at most, every visitor needs it whole, and inlining it keeps
// the prerendered page readable with scripts blocked.
export const load: PageLoad = async ({ fetch }) => {
	const [guesses, terms] = await Promise.all([getGuesses(fetch), getTerms(fetch)]);
	return { guesses, terms };
};
