import { getBuild, type Build } from '$lib/data';
import type { LayoutLoad } from './$types';

// Every page is prerendered: the site is served as static files, so nothing
// can be rendered on request.
export const prerender = true;
// Pages serves /about/ as about/index.html. Always emitting the trailing slash
// keeps links, prerendered files and the URLs Pages answers in agreement.
export const trailingSlash = 'always';

export const load: LayoutLoad = async ({ fetch }) => {
	// The footer's build date is the only thing the layout needs. If it cannot
	// load, the footer leaves the date out: a failing root layout would
	// replace every page, including the not-found page, with SvelteKit's
	// unstyled fallback error.
	let build: Build | null = null;
	try {
		build = await getBuild(fetch);
	} catch {
		build = null;
	}
	return { build };
};
