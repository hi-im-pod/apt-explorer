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
	ReportsShard,
	Resolution,
	Sources,
	Trends,
	Vulns
} from './types';

export type * from './types';

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

export function getActorsIndex(fetch: Fetch): Promise<ActorsIndex> {
	return getJson(fetch, 'actors/index.json');
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

export function getCampaigns(fetch: Fetch): Promise<Campaigns> {
	return getJson(fetch, 'campaigns.json');
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
