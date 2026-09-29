import { getActorsIndex } from '$lib/data';
import type { PageLoad } from './$types';

// A universal load: the index is one file that every visitor needs whole, so
// inlining it into the prerendered page costs nothing extra, and a
// client-side visit fetches the same file.
export const load: PageLoad = async ({ fetch }) => ({ actors: await getActorsIndex(fetch) });
