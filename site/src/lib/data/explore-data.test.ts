// The explore page's data: a small index first, then one shard on demand.
import { describe, expect, it, vi } from 'vitest';
vi.mock('$app/paths', () => ({ base: '/apt-explorer' }));
import {
	getExploreData,
	getFreshBuild,
	getReportDetail,
	getReportShard,
	getReportsIndex
} from './index';

const BUILT = '2026-09-28T03:21:05Z';
const V = `?v=${encodeURIComponent(BUILT)}`;
const build = { built_at: BUILT, version: 'x', report_years: [2024], report_count: 0, recent_since: '2024-07-01', recent_months: 24 };
const SHA = 'ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12';
const indexFile = (built_at = BUILT) => ({
	built_at,
	id_len: 8,
	total: 1,
	tables: { sources: [], organisations: [], actors: [], cves: [], techniques: [] },
	kev: [],
	columns: {
		id: [SHA.slice(0, 8)],
		title: ['T'],
		published: ['2024-05-01'],
		organisation: [null],
		sources: [1],
		actors: [[]],
		actors_from_title: [[]],
		cves: [[]],
		techniques: [[]]
	}
});
const fullReport = { id: SHA, title: 'T', published: '2024-05-01', url: 'https://ex.org/t', url_ok: true };

/**
 * A fetch that answers each URL from a list, one entry per request and the
 * last entry for every request after that, and records what it was asked.
 */
function scripted(script: Record<string, unknown[]>) {
	const calls: { url: string; init?: RequestInit }[] = [];
	const seen = new Map<string, number>();
	const fn = vi.fn(async (url: string, init?: RequestInit) => {
		calls.push({ url, init });
		const queue = script[url];
		if (!queue?.length) return new Response('missing', { status: 404 });
		const n = seen.get(url) ?? 0;
		seen.set(url, n + 1);
		const next = queue[Math.min(n, queue.length - 1)];
		return next instanceof Response ? next.clone() : new Response(JSON.stringify(next));
	});
	return Object.assign(fn, { calls });
}
const asFetch = (f: unknown) => f as unknown as typeof fetch;

describe('getFreshBuild', () => {
	it('asks the server whether build.json changed, so a new build is never missed', async () => {
		const f = scripted({ '/apt-explorer/data/build.json': [build] });
		expect(await getFreshBuild(asFetch(f))).toEqual(build);
		expect(f.calls[0].init).toEqual({ cache: 'no-cache' });
	});
});

describe('getReportsIndex', () => {
	const url = `/apt-explorer/data/reports/index.json${V}`;

	it('reads the index under the build time, reusing any stored copy', async () => {
		const f = scripted({ [url]: [indexFile()] });
		const idx = await getReportsIndex(asFetch(f), build);
		expect(idx.total).toBe(1);
		expect(f.calls).toEqual([{ url, init: { cache: 'force-cache' } }]);
	});

	it('replaces a copy from the wrong build, once, and then accepts the right one', async () => {
		const f = scripted({ [url]: [indexFile('2020-01-01T00:00:00Z'), indexFile()] });
		const idx = await getReportsIndex(asFetch(f), build);
		expect(idx.built_at).toBe(BUILT);
		expect(f.calls.map((c) => c.init)).toEqual([{ cache: 'force-cache' }, { cache: 'reload' }]);
	});

	it('gives up with a 409 when the network too returns another build', async () => {
		const f = scripted({ [url]: [indexFile('2020-01-01T00:00:00Z')] });
		await expect(getReportsIndex(asFetch(f), build)).rejects.toMatchObject({ status: 409 });
		expect(f).toHaveBeenCalledTimes(2);
	});

	it('carries the status of a failed request', async () => {
		const f = scripted({ [url]: [new Response('no', { status: 503 })] });
		await expect(getReportsIndex(asFetch(f), build)).rejects.toMatchObject({ status: 503 });
	});
});

describe('getReportShard', () => {
	it('reads one year under the build time', async () => {
		const b = { ...build, built_at: '2026-01-01T00:00:00Z' };
		const url = '/apt-explorer/data/reports/2024.json?v=2026-01-01T00%3A00%3A00Z';
		const f = scripted({ [url]: [[fullReport]] });
		expect(await getReportShard(asFetch(f), b, '2024')).toEqual([fullReport]);
		expect(f.calls[0]).toEqual({ url, init: { cache: 'force-cache' } });
	});

	it('reads each shard once per build, however often it is asked', async () => {
		const b = { ...build, built_at: '2026-02-01T00:00:00Z' };
		const f = scripted({ '/apt-explorer/data/reports/2023.json?v=2026-02-01T00%3A00%3A00Z': [[]] });
		await Promise.all([getReportShard(asFetch(f), b, '2023'), getReportShard(asFetch(f), b, '2023')]);
		await getReportShard(asFetch(f), b, '2023');
		expect(f).toHaveBeenCalledTimes(1);
	});

	it('does not remember a failure, so a retry asks again', async () => {
		const b = { ...build, built_at: '2026-03-01T00:00:00Z' };
		const url = '/apt-explorer/data/reports/2022.json?v=2026-03-01T00%3A00%3A00Z';
		const f = scripted({ [url]: [new Response('down', { status: 503 }), []] });
		await expect(getReportShard(asFetch(f), b, '2022')).rejects.toMatchObject({ status: 503 });
		await expect(getReportShard(asFetch(f), b, '2022')).resolves.toEqual([]);
	});

	it('refuses a shard name that is not a year or undated', async () => {
		const f = scripted({});
		await expect(getReportShard(asFetch(f), build, '../build')).rejects.toMatchObject({ status: 404 });
		expect(f).not.toHaveBeenCalled();
	});
});

describe('getReportDetail', () => {
	const b = { ...build, built_at: '2026-04-01T00:00:00Z' };
	const url = '/apt-explorer/data/reports/2024.json?v=2026-04-01T00%3A00%3A00Z';
	const row = { id: SHA.slice(0, 8), published: '2024-05-01' };

	it('finds the report in the shard for its year by the id the index holds', async () => {
		const other = { ...fullReport, id: 'f'.repeat(40) };
		const f = scripted({ [url]: [[other, fullReport]] });
		expect(await getReportDetail(asFetch(f), b, 8, row)).toEqual(fullReport);
	});

	it('reads the undated shard for a report with no date', async () => {
		const undatedUrl = '/apt-explorer/data/reports/undated.json?v=2026-04-01T00%3A00%3A00Z';
		const f = scripted({ [undatedUrl]: [[{ ...fullReport, published: null }]] });
		const r = await getReportDetail(asFetch(f), b, 8, { ...row, published: null });
		expect(r.published).toBeNull();
	});

	it('reloads the shard once when the report is not in it, in case the copy is from another build', async () => {
		const b2 = { ...b, built_at: '2026-05-01T00:00:00Z' };
		const url2 = '/apt-explorer/data/reports/2024.json?v=2026-05-01T00%3A00%3A00Z';
		const f = scripted({ [url2]: [[], [fullReport]] });
		expect(await getReportDetail(asFetch(f), b2, 8, row)).toEqual(fullReport);
		expect(f.calls.map((c) => c.init)).toEqual([{ cache: 'force-cache' }, { cache: 'reload' }]);
	});

	it('says not found when even a fresh shard lacks the report', async () => {
		const b3 = { ...b, built_at: '2026-06-01T00:00:00Z' };
		const url3 = '/apt-explorer/data/reports/2024.json?v=2026-06-01T00%3A00%3A00Z';
		const f = scripted({ [url3]: [[]] });
		await expect(getReportDetail(asFetch(f), b3, 8, row)).rejects.toMatchObject({ status: 404 });
	});
});

describe('getExploreData', () => {
	const files = (over: Record<string, unknown[]> = {}) => ({
		'/apt-explorer/data/build.json': [build],
		[`/apt-explorer/data/reports/index.json${V}`]: [indexFile()],
		[`/apt-explorer/data/campaigns.json${V}`]: [[]],
		[`/apt-explorer/data/actors/index.json${V}`]: [[]],
		...over
	});

	it('reads the build time first, then the index, campaigns and actors under it', async () => {
		const f = scripted(files());
		const data = await getExploreData(asFetch(f));
		expect(data.build).toEqual(build);
		expect(data.index.total).toBe(1);
		expect(f.calls[0].url).toBe('/apt-explorer/data/build.json');
		expect(
			f.calls
				.slice(1)
				.map((c) => c.url)
				.sort()
		).toEqual([
			`/apt-explorer/data/actors/index.json${V}`,
			`/apt-explorer/data/campaigns.json${V}`,
			`/apt-explorer/data/reports/index.json${V}`
		]);
	});

	it('does not fetch any report shard or the vulnerability list', async () => {
		const f = scripted(files());
		await getExploreData(asFetch(f));
		expect(f.calls.some((c) => /reports\/\d|undated|vulns/.test(c.url))).toBe(false);
	});

	it('starts again from build.json when a new build lands while it is loading', async () => {
		const newer = { ...build, built_at: '2026-09-29T00:00:00Z' };
		const NV = `?v=${encodeURIComponent(newer.built_at)}`;
		const f = scripted({
			'/apt-explorer/data/build.json': [build, newer],
			// The old address now serves the new file, as a host does mid-deploy.
			[`/apt-explorer/data/reports/index.json${V}`]: [indexFile(newer.built_at)],
			[`/apt-explorer/data/reports/index.json${NV}`]: [indexFile(newer.built_at)],
			[`/apt-explorer/data/campaigns.json${V}`]: [[]],
			[`/apt-explorer/data/campaigns.json${NV}`]: [[]],
			[`/apt-explorer/data/actors/index.json${V}`]: [[]],
			[`/apt-explorer/data/actors/index.json${NV}`]: [[]]
		});
		const data = await getExploreData(asFetch(f));
		expect(data.build.built_at).toBe(newer.built_at);
	});

	it('fails with the status when a file is missing', async () => {
		const f = scripted(files({ [`/apt-explorer/data/campaigns.json${V}`]: [new Response('x', { status: 500 })] }));
		await expect(getExploreData(asFetch(f))).rejects.toMatchObject({ status: 500 });
	});
});
