import { test, expect, type Page } from '@playwright/test';
import type { Campaigns } from '../src/lib/data/types';
import { INDEX, SHARD, build, index, read, reports, short } from './explore-data';

// How the explore page behaves while its data is loading, slow, wrong or
// missing. These run against the preview server with the service worker
// blocked, so page.route sees every request. Return visits and offline use are
// in explore-cache.spec.ts, which runs with the worker.

const EXPLORE = '/apt-explorer/explore/';
const campaigns = read<Campaigns>('campaigns.json');
const TOTAL = index.total + campaigns.length;

/** The page's own count and loading note, not the status line inside the open panel. */
const status = (page: Page) => page.locator('.notice[role="status"]');
const table = (page: Page) => page.getByRole('table', { name: /reports and campaigns/i });
const bodyRows = (page: Page) => table(page).getByRole('row').filter({ has: page.getByRole('cell') });

// The first dated report, which the panel reads from its year shard.
const sample = reports.find((r) => r.published != null)!;
const sampleYear = sample.published!.slice(0, 4);

for (const width of [1280, 375]) {
	test(`cold load at ${width}px: the index is the only report data, and rows show the full count`, async ({ page }, testInfo) => {
		await page.setViewportSize({ width, height: 900 });
		const seen: string[] = [];
		page.on('request', (r) => seen.push(new URL(r.url()).pathname + new URL(r.url()).search));
		await page.goto(EXPLORE);
		await expect(status(page)).toContainText(`of ${TOTAL.toLocaleString('en-US')} reports and campaigns`, { timeout: 20_000 });

		// Report data is one request for the index, under a URL that carries the build time.
		const data = seen.filter((u) => u.includes('/data/reports/'));
		expect(data).toEqual([`/apt-explorer/data/reports/index.json?v=${encodeURIComponent(build.built_at)}`]);

		// The first row is on screen and inside the viewport.
		const first = bodyRows(page).first();
		await expect(first).toBeInViewport();
		const box = (await first.boundingBox())!;
		expect(box.x).toBeGreaterThanOrEqual(0);
		expect(box.x + box.width).toBeLessThanOrEqual(width);
		expect(box.height).toBeGreaterThan(20);
		await page.screenshot({ path: testInfo.outputPath(`ready-${width}.png`) });
	});
}

test('a slow line gets a note that says why, and the table still arrives', async ({ page }) => {
	await page.route(INDEX, async (route) => {
		await new Promise((done) => setTimeout(done, 4600));
		await route.continue();
	});
	await page.goto(EXPLORE);
	await expect(status(page)).toContainText('Loading reports and campaigns');
	await expect(status(page)).toContainText('This is taking a while', { timeout: 8000 });
	await expect(status(page)).toContainText('about 1 MB');
	await expect(status(page)).toContainText(/showing/i, { timeout: 20_000 });
	// The note goes away once the rows are there.
	await expect(status(page)).not.toContainText('taking a while');
});

for (const width of [1280, 375]) {
	test(`an index that fails to load shows an error with a retry button at ${width}px, and the retry works`, async ({ page }, testInfo) => {
		await page.setViewportSize({ width, height: 800 });
		await page.route(INDEX, (route) => route.fulfill({ status: 500, body: 'no' }));
		await page.goto(EXPLORE);
		const alert = page.getByRole('alert');
		await expect(alert).toContainText('The report list could not be loaded. Check your connection, then try again.');
		await expect(table(page)).toHaveCount(0);

		const retry = alert.getByRole('button', { name: 'Try again' });
		const box = (await retry.boundingBox())!;
		expect(box.x).toBeGreaterThanOrEqual(0);
		expect(box.x + box.width).toBeLessThanOrEqual(width);
		// A finger has to be able to hit it.
		expect(box.height).toBeGreaterThanOrEqual(24);
		// The error is set apart from the page by its accent border, so it does not read as ordinary text.
		expect(await alert.evaluate((el) => getComputedStyle(el).borderLeftWidth)).toBe('3px');
		await page.screenshot({ path: testInfo.outputPath(`index-error-${width}.png`) });

		await page.unroute(INDEX);
		await retry.click();
		await expect(status(page)).toContainText(`of ${TOTAL.toLocaleString('en-US')}`, { timeout: 20_000 });
		await expect(alert).toHaveCount(0);
		await expect(bodyRows(page).first()).toBeVisible();
	});
}

test('an index from another build is never shown: the page reports an error instead', async ({ page }) => {
	// This is what a stale cached copy looks like to the page. It must not
	// show the old rows under the new build, and a retry that gets the same
	// stale copy must end in the error, not in a loop.
	let asked = 0;
	await page.route(INDEX, async (route) => {
		asked += 1;
		const body = await (await route.fetch()).json();
		await route.fulfill({ json: { ...body, built_at: '2000-01-01T00:00:00Z' } });
	});
	await page.goto(EXPLORE);
	await expect(page.getByRole('alert')).toContainText(/could not be loaded/i, { timeout: 20_000 });
	await expect(table(page)).toHaveCount(0);
	// Each attempt asks twice (the second time telling the network to skip its copy), and the
	// page starts over once from build.json in case a new build landed in between. Then it stops.
	expect(asked).toBe(4);
});

test('the browser says it is offline, and there is no saved copy: the error says so', async ({ page }) => {
	// The page shell comes from the preview server, so only the data requests are failed, and
	// navigator.onLine is set to false. That is what a visitor with no connection and no saved
	// copy sees once the page itself has opened.
	await page.route(/\/data\//, (route) => route.abort('internetdisconnected'));
	await page.addInitScript(() => {
		Object.defineProperty(navigator, 'onLine', { get: () => false });
	});
	await page.goto(EXPLORE);
	await expect(page.getByRole('alert')).toContainText(
		'You are offline, and this browser has no saved copy of the report list. Connect to the internet, then try again.'
	);
});

test.describe('the panel reads its links from one year shard', () => {
	test('the panel shows the report at once, and only that year is fetched', async ({ page }) => {
		const shards: string[] = [];
		page.on('request', (r) => {
			const m = SHARD.exec(r.url());
			if (m) shards.push(m[1]);
		});
		await page.goto(`${EXPLORE}?report=${short(sample.id)}`);
		const dialog = page.getByRole('dialog');
		await expect(dialog.getByRole('heading', { level: 2 })).toHaveText(sample.title, { timeout: 20_000 });
		await expect(dialog.getByRole('list', { name: /links/i })).toBeVisible();
		expect(shards).toEqual([sampleYear]);
	});

	test('a shard that fails shows an error with a retry, and the retry fills in the links', async ({ page }, testInfo) => {
		let fail = true;
		await page.route(SHARD, (route) => (fail ? route.fulfill({ status: 500, body: 'no' }) : route.continue()));
		await page.goto(`${EXPLORE}?report=${short(sample.id)}`);
		const dialog = page.getByRole('dialog');
		// The row's own fields do not wait for the shard.
		await expect(dialog.getByRole('heading', { level: 2 })).toHaveText(sample.title, { timeout: 20_000 });
		await expect(dialog).toContainText('The links for this report could not be loaded.');
		await expect(dialog.getByRole('list', { name: /links/i })).toHaveCount(0);
		// The table behind the panel still works.
		await expect(status(page)).toContainText(/showing/i);
		await page.screenshot({ path: testInfo.outputPath('panel-error.png') });

		fail = false;
		await dialog.getByRole('button', { name: 'Try again' }).click();
		await expect(dialog.getByRole('list', { name: /links/i })).toBeVisible();
		await expect(dialog).not.toContainText('could not be loaded');
	});

	test('while the shard loads the panel says so', async ({ page }) => {
		await page.route(SHARD, async (route) => {
			await new Promise((done) => setTimeout(done, 1500));
			await route.continue();
		});
		await page.goto(`${EXPLORE}?report=${short(sample.id)}`);
		const dialog = page.getByRole('dialog');
		await expect(dialog).toContainText('Loading the links for this report…', { timeout: 20_000 });
		await expect(dialog.getByRole('list', { name: /links/i })).toBeVisible({ timeout: 10_000 });
	});
});

test.describe('without scripts', () => {
	test.use({ javaScriptEnabled: false });

	for (const width of [1280, 375]) {
		test(`at ${width}px the page says what it needs scripts for, and what still works`, async ({ page }, testInfo) => {
			await page.setViewportSize({ width, height: 800 });
			await page.goto(EXPLORE);
			await expect(page.getByRole('heading', { level: 1 })).toHaveText('Explore');
			const note = status(page);
			// Playwright compares text with runs of white space folded into one space.
			await expect(note).toHaveText(
				'This table is built in your browser, so it needs scripts to run. Actor pages and the About page work without them.'
			);
			// The note is on the first screen and not clipped by the viewport.
			const box = (await note.boundingBox())!;
			expect(box.x).toBeGreaterThanOrEqual(0);
			expect(box.x + box.width).toBeLessThanOrEqual(width);
			expect(box.y).toBeLessThan(800);
			expect(await note.evaluate((el) => getComputedStyle(el).display)).not.toBe('none');
			await expect(table(page)).toHaveCount(0);
			// What the note promises: the actor and About pages open with no scripts.
			await page.getByRole('link', { name: 'About', exact: true }).first().click();
			await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
			await page.screenshot({ path: testInfo.outputPath(`no-scripts-${width}.png`) });
		});
	}
});
