import { getActorsIndex, getResolution, getSources } from '$lib/data';
import type { PageLoad } from './$types';

// A universal load, like the About page: all three files are small, every
// visitor to this page needs them whole, and inlining them keeps the
// prerendered page readable with scripts blocked. The actors index is here
// only so an ambiguity can name its candidates instead of printing IDs.
export const load: PageLoad = async ({ fetch }) => {
	const [resolution, sources, actors] = await Promise.all([
		getResolution(fetch),
		getSources(fetch),
		getActorsIndex(fetch)
	]);
	return { resolution, sources, actors };
};
