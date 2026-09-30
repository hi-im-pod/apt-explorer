/**
 * How the site keeps data between visits without ever showing an old build.
 *
 * Nothing here is a timer or a guess. Every data file the explore page reads
 * is asked for under a URL that contains the build time from build.json, such
 * as reports/index.json?v=2026-09-28T03%3A21%3A05Z. GitHub Pages ignores the
 * query and serves the same file, but a browser treats each build's URL as a
 * different address. A copy kept under one build's address can therefore be
 * reused with no check at all, and a new build finds nothing under its own
 * address and fetches. Only build.json is asked afresh each visit, and it is
 * a few hundred bytes.
 *
 * Two layers keep the copies. The browser's HTTP cache does it for every
 * visitor. The service worker (src/service-worker.ts) adds a store that
 * survives the HTTP cache being trimmed and lets the pages open offline. Both
 * follow the rules in this file, which has no browser-only code so a test can
 * run it.
 */

/** Ask the server whether the copy is still current, and use the copy only if it is. */
export const REVALIDATE = { cache: 'no-cache' } as const;

/** Use a stored copy whatever its age. Safe only for a URL that carries a build time. */
export const REUSE = { cache: 'force-cache' } as const;

/** Skip every stored copy and replace it. Used when a copy turned out to be from the wrong build. */
export const RELOAD = { cache: 'reload' } as const;

/** The service worker's store for versioned data. Its name does not change with the app, because data is versioned by its own URLs. */
export const DATA_CACHE = 'aptx-data';

/** The query key that carries the build time. */
const VERSION_KEY = 'v';

/** `path` with the build time added, so a new build is a new address. */
export function versioned(path: string, builtAt: string): string {
	return `${path}?${VERSION_KEY}=${encodeURIComponent(builtAt)}`;
}

/** The build time a URL carries, or null when it has none. */
export function versionOf(url: URL): string | null {
	return url.searchParams.get(VERSION_KEY);
}

/**
 * What the service worker does with a request.
 *
 * - versioned-data: answer from the store if it holds the URL, else fetch and keep it.
 * - immutable: the same, for app files whose names contain a hash of their content.
 * - network-first: fetch, keep the answer, and fall back to the kept copy only when the
 *   network fails. This is what makes a new build appear at once and an offline visit work.
 * - bypass: not the worker's business.
 */
export type CachePlan = 'versioned-data' | 'immutable' | 'network-first' | 'bypass';

export function planFor(
	request: { url: string; method: string; cache: string },
	origin: string,
	base: string
): CachePlan {
	if (request.method !== 'GET') return 'bypass';
	const url = new URL(request.url);
	if (url.origin !== origin) return 'bypass';
	// "/apt-explorer-old/" starts with "/apt-explorer" but is another site.
	if (base && url.pathname !== base && !url.pathname.startsWith(`${base}/`)) return 'bypass';
	const path = url.pathname.slice(base.length);
	if (path.startsWith('/_app/immutable/')) return 'immutable';
	// A page that asks for "reload" or "no-cache" has decided the copy it has is not to be trusted.
	if (path.startsWith('/data/') && versionOf(url) != null && request.cache !== 'reload' && request.cache !== 'no-cache') {
		return 'versioned-data';
	}
	return 'network-first';
}

/**
 * The stored URLs to delete once `fresh` has been stored: every copy that
 * belongs to another build. An old build's files can never be asked for
 * again, so keeping them would only grow the store.
 */
export function pruneTargets(stored: readonly string[], fresh: string): string[] {
	const current = versionOf(new URL(fresh));
	return stored.filter((url) => versionOf(new URL(url)) !== current);
}
