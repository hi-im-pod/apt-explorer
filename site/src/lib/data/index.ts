/**
 * The only place the site reads data from.
 *
 * Every getter takes the fetch it should use. Pass SvelteKit's fetch from a
 * load function: during prerender it reads static/data from the build, and
 * the responses it records are inlined into the page, so the browser does
 * not fetch them again. Today the files are static JSON under the base path.
 * On a server these functions can call an API that returns the same shapes,
 * and nothing that imports them has to change.
 */
import { base } from '$app/paths';
import type {
	Actor,
	ActorsIndex,
	Build,
	Campaigns,
	Report,
	ReportsIndex,
	ReportsShard,
	Resolution,
	Sources,
	Trends,
	Vulns
} from './types';

import { RELOAD, REUSE, REVALIDATE, versioned } from '../cache';
import { shortId } from './report-id';

export type * from './types';
export { indexForm, shortId } from './report-id';

type Fetch = typeof fetch;

/**
 * A data file could not be read. `status` is the HTTP status, so a load
 * function can turn a missing actor into its own 404 with `error(e.status)`.
 */
export class DataError extends Error {
	readonly status: number;

	constructor(status: number, message: string) {
		super(message);
		this.name = 'DataError';
		this.status = status;
	}
}

async function getJson<T>(fetch: Fetch, path: string): Promise<T> {
	const url = `${base}/data/${path}`;
	const res = await fetch(url);
	if (!res.ok) throw new DataError(res.status, `Could not load ${url} (HTTP ${res.status})`);
	return (await res.json()) as T;
}

/**
 * The same read for a file that is asked for under a build time, so the
 * browser can keep the copy with no check (see cache.ts). `init` says whether
 * a stored copy may be used or must be replaced.
 */
async function getVersionedJson<T>(fetch: Fetch, path: string, builtAt: string, init: RequestInit = REUSE): Promise<T> {
	const url = versioned(`${base}/data/${path}`, builtAt);
	const res = await fetch(url, init);
	if (!res.ok) throw new DataError(res.status, `Could not load ${url} (HTTP ${res.status})`);
	return (await res.json()) as T;
}

/**
 * Without a build the file is read as it always was. With one it is read
 * under that build's address, which is what the explore page does.
 */
export function getActorsIndex(fetch: Fetch, build?: Build): Promise<ActorsIndex> {
	return build ? getVersionedJson(fetch, 'actors/index.json', build.built_at) : getJson(fetch, 'actors/index.json');
}

/**
 * The ID comes from the URL, so it is encoded: "../build" must ask for a
 * file named "..%2Fbuild.json" inside actors/, which does not exist, and
 * never for build.json one level up.
 */
export function getActor(fetch: Fetch, id: string): Promise<Actor> {
	return getJson(fetch, `actors/${encodeURIComponent(id)}.json`);
}

/**
 * Reports for the given years, oldest shard first. 'all' adds the undated
 * reports at the end.
 *
 * A static host cannot list a directory, so 'all' takes the years from
 * build.json instead of probing: each probe for a missing year would be a
 * 404, and during prerender a 404 fails the build. A missing shard that was
 * asked for is an error, never a silently shorter list.
 */
export async function getReports(fetch: Fetch, years: number[] | 'all'): Promise<Report[]> {
	const all = years === 'all';
	const wanted = all ? (await getBuild(fetch)).report_years : years;
	const paths = wanted.map((y) => `reports/${y}.json`);
	if (all) paths.push('reports/undated.json');
	const shards = await Promise.all(paths.map((p) => getJson<ReportsShard>(fetch, p)));
	return shards.flat();
}

export function getCampaigns(fetch: Fetch, build?: Build): Promise<Campaigns> {
	return build ? getVersionedJson(fetch, 'campaigns.json', build.built_at) : getJson(fetch, 'campaigns.json');
}

/** build.json as it is on the server now. It is a few hundred bytes, and every other explore file is addressed by its built_at. */
export async function getFreshBuild(fetch: Fetch): Promise<Build> {
	const url = `${base}/data/build.json`;
	const res = await fetch(url, REVALIDATE);
	if (!res.ok) throw new DataError(res.status, `Could not load ${url} (HTTP ${res.status})`);
	return (await res.json()) as Build;
}

/**
 * The index and the build.json it was asked under must come from the same
 * build. A copy from another build (an old tab, a cache filled mid-deploy) is
 * replaced once from the network. If the network too disagrees, a deploy is
 * in progress, and 409 tells the caller to start again from build.json.
 */
export async function getReportsIndex(fetch: Fetch, build: Build): Promise<ReportsIndex> {
	const first = await getVersionedJson<ReportsIndex>(fetch, 'reports/index.json', build.built_at, REUSE);
	if (first.built_at === build.built_at) return first;
	const second = await getVersionedJson<ReportsIndex>(fetch, 'reports/index.json', build.built_at, RELOAD);
	if (second.built_at === build.built_at) return second;
	throw new DataError(409, `The report index is from build ${second.built_at}, not ${build.built_at}`);
}

/** Shards already asked for, by URL, so opening ten reports of one year reads one file. */
const shards = new Map<string, Promise<ReportsShard>>();

const SHARD_KEY = /^(\d{4}|undated)$/;

/**
 * One shard by year, or 'undated'. The key is checked first because it can
 * come from a link, and only these two shapes are shard names.
 *
 * A failure is forgotten at once, so pressing Retry asks again.
 */
export function getReportShard(fetch: Fetch, build: Build, key: string, init: RequestInit = REUSE): Promise<ReportsShard> {
	if (!SHARD_KEY.test(key)) return Promise.reject(new DataError(404, `There is no report shard named ${key}`));
	const url = versioned(`${base}/data/reports/${key}.json`, build.built_at);
	const known = init === REUSE ? shards.get(url) : undefined;
	if (known) return known;
	const pending = getVersionedJson<ReportsShard>(fetch, `reports/${key}.json`, build.built_at, init);
	shards.set(url, pending);
	pending.catch(() => {
		if (shards.get(url) === pending) shards.delete(url);
	});
	return pending;
}

/**
 * The full record of one report, from the shard of its year. The index holds
 * the short id and the date, which is all it takes to find the shard and the
 * report. A report that is not in the shard may mean the stored shard is from
 * another build, so the shard is replaced once before saying not found.
 */
export async function getReportDetail(
	fetch: Fetch,
	build: Build,
	idLen: number,
	row: { id: string; published: string | null }
): Promise<Report> {
	const key = row.published ? row.published.slice(0, 4) : 'undated';
	const find = (list: ReportsShard) => list.find((r) => shortId(r.id, idLen) === row.id);
	const found = find(await getReportShard(fetch, build, key));
	if (found) return found;
	const fresh = find(await getReportShard(fetch, build, key, RELOAD));
	if (fresh) return fresh;
	throw new DataError(404, `Report ${row.id} is not in the ${key} shard`);
}

export type ExploreData = {
	build: Build;
	index: ReportsIndex;
	campaigns: Campaigns;
	actors: ActorsIndex;
};

/**
 * Everything the explore table needs to list, filter and search: the index,
 * the campaigns and the actor names. No report shard and no vulnerability
 * list, because opening a report reads its shard then.
 *
 * If a new build lands while this is loading, the parts can disagree. The
 * index check catches that with a 409, and the load then starts again from
 * build.json, once.
 */
export async function getExploreData(fetch: Fetch): Promise<ExploreData> {
	for (let attempt = 0; ; attempt++) {
		const build = await getFreshBuild(fetch);
		try {
			const [index, campaigns, actors] = await Promise.all([
				getReportsIndex(fetch, build),
				getCampaigns(fetch, build),
				getActorsIndex(fetch, build)
			]);
			return { build, index, campaigns, actors };
		} catch (e) {
			if (attempt > 0 || !(e instanceof DataError) || e.status !== 409) throw e;
		}
	}
}

export function getVulns(fetch: Fetch): Promise<Vulns> {
	return getJson(fetch, 'vulns.json');
}

export function getTrends(fetch: Fetch): Promise<Trends> {
	return getJson(fetch, 'trends.json');
}

export function getSources(fetch: Fetch): Promise<Sources> {
	return getJson(fetch, 'sources.json');
}

export function getResolution(fetch: Fetch): Promise<Resolution> {
	return getJson(fetch, 'resolution.json');
}

export function getBuild(fetch: Fetch): Promise<Build> {
	return getJson(fetch, 'build.json');
}
