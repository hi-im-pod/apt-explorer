import { describe, it, expect, vi } from 'vitest';
vi.mock('$app/paths', () => ({ base: '/apt-explorer' }));
import {
	getActor,
	getActorsIndex,
	getBuild,
	getCampaigns,
	getGuesses,
	getReports,
	getResolution,
	getSources,
	getTrends,
	getVulns
} from './index';

describe('data layer', () => {
	it('fetches under the base path', async () => {
		const f = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'G0007', name: 'APT28' })));
		const a = await getActor(f as unknown as typeof fetch, 'G0007');
		expect(f).toHaveBeenCalledWith('/apt-explorer/data/actors/G0007.json');
		expect(a.name).toBe('APT28');
	});
	it('throws a 404-shaped error for an unknown actor', async () => {
		const f = vi.fn().mockResolvedValue(new Response('nope', { status: 404 }));
		await expect(getActor(f as unknown as typeof fetch, 'zzz')).rejects.toMatchObject({ status: 404 });
	});
});

/** A fetch stub that answers each URL from a map, with a fresh Response per call. */
function stubFetch(files: Record<string, unknown>) {
	return vi.fn(async (url: string) =>
		url in files
			? new Response(JSON.stringify(files[url]))
			: new Response('missing', { status: 404 })
	);
}

describe('data layer URLs', () => {
	it.each([
		['getActorsIndex', getActorsIndex, '/apt-explorer/data/actors/index.json'],
		['getCampaigns', getCampaigns, '/apt-explorer/data/campaigns.json'],
		['getVulns', getVulns, '/apt-explorer/data/vulns.json'],
		['getTrends', getTrends, '/apt-explorer/data/trends.json'],
		['getGuesses', getGuesses, '/apt-explorer/data/guesses.json'],
		['getSources', getSources, '/apt-explorer/data/sources.json'],
		['getResolution', getResolution, '/apt-explorer/data/resolution.json'],
		['getBuild', getBuild, '/apt-explorer/data/build.json']
	] as const)('%s reads %s', async (_name, getter, url) => {
		const f = stubFetch({ [url]: [] });
		await getter(f as unknown as typeof fetch);
		expect(f).toHaveBeenCalledTimes(1);
		expect(f).toHaveBeenCalledWith(url);
	});

	it('escapes an actor ID so it cannot leave the actors directory', async () => {
		const f = stubFetch({});
		await expect(getActor(f as unknown as typeof fetch, '../build')).rejects.toMatchObject({ status: 404 });
		expect(f).toHaveBeenCalledWith('/apt-explorer/data/actors/..%2Fbuild.json');
	});

	it('carries the status and a message on any non-OK response', async () => {
		const f = vi.fn().mockResolvedValue(new Response('boom', { status: 503 }));
		const err = await getTrends(f as unknown as typeof fetch).catch((e) => e);
		expect(err).toMatchObject({ status: 503 });
		expect(err.message).toContain('/apt-explorer/data/trends.json');
	});
});

describe('getReports', () => {
	const r = (id: string, published: string | null) => ({ id, published });

	it("'all' reads the shard years from build.json, then every shard and undated.json", async () => {
		const f = stubFetch({
			'/apt-explorer/data/build.json': { built_at: 'x', version: 'x', report_years: [2024, 2026] },
			'/apt-explorer/data/reports/2024.json': [r('a', '2024-02-01')],
			'/apt-explorer/data/reports/2026.json': [r('b', '2026-01-01'), r('c', '2026-03-01')],
			'/apt-explorer/data/reports/undated.json': [r('d', null)]
		});
		const rows = await getReports(f as unknown as typeof fetch, 'all');
		expect(rows.map((x) => x.id)).toEqual(['a', 'b', 'c', 'd']);
		// No probing for years build.json does not list: on a static host each
		// probe would be a 404, and during prerender a 404 fails the build.
		expect(f.mock.calls.map((c) => c[0]).sort()).toEqual([
			'/apt-explorer/data/build.json',
			'/apt-explorer/data/reports/2024.json',
			'/apt-explorer/data/reports/2026.json',
			'/apt-explorer/data/reports/undated.json'
		]);
	});

	it('reads only the years asked for, without build.json or undated.json', async () => {
		const f = stubFetch({ '/apt-explorer/data/reports/2025.json': [r('e', '2025-05-05')] });
		const rows = await getReports(f as unknown as typeof fetch, [2025]);
		expect(rows.map((x) => x.id)).toEqual(['e']);
		expect(f).toHaveBeenCalledTimes(1);
	});

	it('fails when a requested shard is missing rather than returning a partial list', async () => {
		const f = stubFetch({ '/apt-explorer/data/reports/2025.json': [] });
		await expect(getReports(f as unknown as typeof fetch, [2025, 2019])).rejects.toMatchObject({
			status: 404
		});
	});
});
