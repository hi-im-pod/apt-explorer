import { fileURLToPath } from 'node:url';
import { test, expect, type BrowserContext, type Page } from '@playwright/test';
import type { Campaigns } from '../src/lib/data/types';
import { build, index, read, withExtraRows } from './explore-data';
import { startPagesServer } from '../scripts/pages-server.mjs';

// Return visits, offline use and a new build, with the service worker allowed.
//
// The other explore specs block the worker so page.route can see everything.
// These run the built site behind a small server that answers the way GitHub
// Pages does (compression, ten-minute cache headers, ETags), and count what
// reaches it. Playwright cannot see a request a worker answers, so the server
// is what tells us whether the network was used.
//
// The tests share one server and change the files it serves, so they run one
// after another.

test.describe.configure({ mode: 'serial' });

const BASE = '/apt-explorer';
const EXPLORE = `${BASE}/explore/`;
const PORT = Number(process.env.PW_PORT ?? 4173) + 1000;
const campaigns = read<Campaigns>('campaigns.json');
const TOTAL = index.total + campaigns.length;

type Server = Awaited<ReturnType<typeof startPagesServer>>;
let server: Server;

test.beforeAll(async () => {
	server = await startPagesServer({
		dir: fileURLToPath(new URL('../build', import.meta.url)),
		base: BASE,
		port: PORT,
		maxAge: 600
	});
});
test.afterAll(async () => {
	await server.close();
});
test.beforeEach(() => {
	for (const p of ['data/build.json', 'data/reports/index.json']) server.override(p, null);
	server.requests.length = 0;
});

const status = (page: Page) => page.locator('.notice[role="status"]');
const url = (path = EXPLORE) => `${server.url}${path}`;
/** Requests that reached the server for report data, with their queries. */
const reportRequests = () => server.requests.filter((r: string) => r.includes('/data/reports/'));

async function ready(page: Page, count = TOTAL) {
	await expect(status(page)).toContainText(`of ${count.toLocaleString('en-US')} reports and campaigns`, {
		timeout: 20_000
	});
	await expect(page.getByRole('table', { name: /reports and campaigns/i }).getByRole('row').nth(1)).toBeVisible();
}

/** Wait until the page is controlled by the worker, which is when its requests are kept. */
async function controlled(page: Page) {
	await page.evaluate(async () => {
		await navigator.serviceWorker.ready;
	});
	await page.reload();
	await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller != null)).toBe(true);
}

/** Open the page twice, so the worker is installed, controls the page, and has kept what the second visit fetched. */
async function warmUp(context: BrowserContext): Promise<Page> {
	const page = await context.newPage();
	await page.goto(url());
	await ready(page);
	await controlled(page);
	await ready(page);
	return page;
}

const keptUrls = (page: Page) =>
	page.evaluate(async () => {
		const out: string[] = [];
		for (const name of await caches.keys()) {
			if (name !== 'aptx-data') continue;
			for (const r of await (await caches.open(name)).keys()) out.push(r.url);
		}
		return out;
	});

test.use({ serviceWorkers: 'allow' });

test('cold: the first visit fetches the index once and no report shard', async ({ page }) => {
	await page.goto(url());
	await ready(page);
	expect(reportRequests()).toEqual([`${BASE}/data/reports/index.json?v=${encodeURIComponent(build.built_at)}`]);
});

test('warm: a return visit sends no request for report data', async ({ context }) => {
	const page = await warmUp(context);
	server.requests.length = 0;
	await page.goto(url());
	await ready(page);
	expect(reportRequests()).toEqual([]);
	// Only the small files that may change are asked for again: the page itself and build.json.
	const asked = server.requests.filter((r: string) => !r.includes('/_app/immutable/'));
	expect(asked.every((r: string) => r === EXPLORE || r === `${BASE}/data/build.json`)).toBe(true);
});

test('offline after a warm visit: the table opens from the kept copy', async ({ context }) => {
	const page = await warmUp(context);
	await context.setOffline(true);
	server.requests.length = 0;
	await page.goto(url(`${EXPLORE}?q=phishing`));
	await expect(status(page)).toContainText(/showing/i, { timeout: 20_000 });
	// The address holds a filter, and the kept page still applies it.
	await expect(page.getByLabel('Search', { exact: true })).toHaveValue('phishing');
	expect(server.requests).toEqual([]);
	await expect(page.getByRole('alert')).toHaveCount(0);
});

test('offline with no warm visit: the page says there is no saved copy', async ({ browser }) => {
	// A context that never visited has nothing to fall back on, but its page is on the server,
	// so the page is opened first and the data requests are failed.
	const context = await browser.newContext({ serviceWorkers: 'block' });
	const page = await context.newPage();
	await page.route(/\/data\//, (route) => route.abort('internetdisconnected'));
	await page.addInitScript(() => {
		Object.defineProperty(navigator, 'onLine', { get: () => false });
	});
	await page.goto(url());
	await expect(page.getByRole('alert')).toContainText('You are offline, and this browser has no saved copy');
	await context.close();
});

test('a new build replaces the kept data: the new rows show, and the old copy is deleted', async ({ context }) => {
	const page = await warmUp(context);
	const before = await keptUrls(page);
	expect(before.length).toBeGreaterThan(0);
	expect(before.every((u) => u.includes(`v=${encodeURIComponent(build.built_at)}`))).toBe(true);

	// A new build: a later time in build.json and in the index, and one report the old one lacks.
	const NEW_AT = '2099-01-01T00:00:00Z';
	const TITLE = 'Zebra crossing report from the new build';
	server.override('data/build.json', JSON.stringify({ ...build, built_at: NEW_AT }));
	server.override(
		'data/reports/index.json',
		JSON.stringify(withExtraRows(index, [{ id: 'synthetic-new', title: TITLE, published: '2099-01-01' }], NEW_AT))
	);
	await page.goto(url(`${EXPLORE}?q=zebra+crossing`));
	await ready(page, TOTAL + 1);
	await expect(page.getByRole('table').getByRole('row').filter({ hasText: TITLE })).toBeVisible();

	// Every kept copy is for the new build, and none of the old build's data is left to be shown.
	await expect
		.poll(async () => (await keptUrls(page)).every((u) => u.includes(`v=${encodeURIComponent(NEW_AT)}`)))
		.toBe(true);
	expect((await keptUrls(page)).length).toBeGreaterThan(0);

	// And offline, the kept copy is the new one.
	await context.setOffline(true);
	await page.goto(url(`${EXPLORE}?q=zebra+crossing`));
	await expect(status(page)).toContainText(/showing/i, { timeout: 20_000 });
	await expect(page.getByRole('table').getByRole('row').filter({ hasText: TITLE })).toBeVisible();
});

test('a build.json that is ahead of the index never shows the old rows', async ({ context }) => {
	// This is the half-published state a cache can produce. The page must ask again, and when
	// the index is still from the other build it must say so rather than show old data.
	const page = await warmUp(context);
	server.override('data/build.json', JSON.stringify({ ...build, built_at: '2098-01-01T00:00:00Z' }));
	await page.goto(url());
	await expect(page.getByRole('alert')).toContainText(/could not be loaded/i, { timeout: 20_000 });
	await expect(page.getByRole('table', { name: /reports and campaigns/i })).toHaveCount(0);
});
