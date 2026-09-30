/// <reference types="@sveltejs/kit" />
/// <reference no-default-lib="true" />
/// <reference lib="esnext" />
/// <reference lib="webworker" />
/**
 * Keeps the site's files between visits and lets a page that was opened
 * before open again with no network.
 *
 * What is kept, and when it is replaced, is decided by `planFor` in
 * $lib/cache, which a unit test covers. This file only carries the plan out
 * against the Cache API:
 *
 * - Versioned data (the URL carries the build time) is answered from the
 *   store when it holds the URL, with no request at all. A new build has new
 *   URLs, so nothing old can ever be answered for it, and the copies of
 *   other builds are deleted once a new one is stored.
 * - Hashed app files are treated the same way, in a store named for the
 *   app version, which is deleted when a new version activates.
 * - Everything else (pages, build.json, unversioned data) asks the network
 *   first, keeps the answer, and falls back to the kept copy only when the
 *   network fails. A new build therefore shows at once, and an offline visit
 *   still gets the last page that was seen.
 */
import { base, version } from '$service-worker';
import { DATA_CACHE, planFor, pruneTargets } from '$lib/cache';

const sw = self as unknown as ServiceWorkerGlobalScope;

const APP_CACHE = `aptx-app-${version}`;

sw.addEventListener('install', () => {
	// A new worker replaces the old one at once. Its rules are the same or
	// newer, and nothing it stores depends on the old worker.
	void sw.skipWaiting();
});

sw.addEventListener('activate', (event) => {
	event.waitUntil(
		(async () => {
			for (const key of await caches.keys()) {
				if (key.startsWith('aptx-app-') && key !== APP_CACHE) await caches.delete(key);
			}
			// Take over the page that registered this worker, so its next
			// requests (and its next reload) are already covered.
			await sw.clients.claim();
		})()
	);
});

sw.addEventListener('fetch', (event) => {
	const { request } = event;
	const plan = planFor(request, sw.location.origin, base);
	if (plan === 'bypass') return;
	event.respondWith(answer(request, plan).catch(() => fetch(request)));
});

/** Where a response for this request is kept. Data that carries a build time goes to the data store. */
function storeFor(request: Request): string {
	const url = new URL(request.url);
	const isVersionedData = url.pathname.startsWith(`${base}/data/`) && url.searchParams.has('v');
	return isVersionedData ? DATA_CACHE : APP_CACHE;
}

/**
 * A page is kept under its address without the query, because the query
 * holds the visitor's filters and every filter would otherwise be a new
 * entry. All of them are the same prerendered page.
 */
function keyFor(request: Request): Request {
	if (request.mode !== 'navigate') return request;
	const url = new URL(request.url);
	url.search = '';
	return new Request(url);
}

async function answer(request: Request, plan: 'versioned-data' | 'immutable' | 'network-first'): Promise<Response> {
	const cache = await caches.open(storeFor(request));
	if (plan !== 'network-first') {
		const hit = await cache.match(request);
		if (hit) return hit;
		// The page asks for a stored copy with "force-cache", so this reuses
		// the browser's own copy too, and nothing crosses the network twice.
		const res = await fetch(request);
		if (res.ok) {
			await cache.put(request, res.clone());
			if (plan === 'versioned-data') await prune(cache, request.url);
		}
		return res;
	}

	try {
		// Pages and build.json are asked afresh each time: the server answers
		// "not modified" for a page that has not changed, which is a few
		// hundred bytes, and a page that has changed arrives whole.
		const res = await fetch(request, request.mode === 'navigate' || isBuildFile(request) ? { cache: 'no-cache' } : undefined);
		if (res.ok) {
			await cache.put(keyFor(request), res.clone());
			// A replaced copy of another build's data has a new build time,
			// so the old ones can go.
			if (storeFor(request) === DATA_CACHE) await prune(cache, request.url);
		}
		return res;
	} catch (offline) {
		const kept = await cache.match(keyFor(request));
		if (kept) return kept;
		throw offline;
	}
}

function isBuildFile(request: Request): boolean {
	return new URL(request.url).pathname === `${base}/data/build.json`;
}

/** Delete the copies of other builds' data once a copy of the newest build is stored. */
async function prune(cache: Cache, freshUrl: string): Promise<void> {
	const stored = (await cache.keys()).map((r) => r.url);
	for (const url of pruneTargets(stored, freshUrl)) await cache.delete(url);
}
