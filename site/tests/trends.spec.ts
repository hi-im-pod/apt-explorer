import { readFileSync } from 'node:fs';
import { test, expect, type Locator, type Page } from '@playwright/test';
import type { ActorsIndex, Trends } from '../src/lib/data/types';
import { sourceLabel } from '../src/lib/data/labels';

// Expectations come from the same data/ the site is built from.
const read = <T>(path: string): T =>
	JSON.parse(readFileSync(new URL(`../../data/${path}`, import.meta.url), 'utf8')) as T;
const trends = read<Trends>('trends.json');
const actors = read<ActorsIndex>('actors/index.json');
const nameOf = (id: string) => actors.find((a) => a.id === id)?.name ?? id;

const TRENDS = '/apt-explorer/trends/';
const themes = ['light', 'dark', 'apt'] as const;
type Key = keyof Trends['notes'];
const KEYS = Object.keys(trends.notes) as Key[];
/** Sections drawn as charts. The other three are a table or a list. */
const CHARTS: Key[] = ['reporting_activity', 'kev_monthly', 'reported_vs_documented'];

const section = (page: Page, key: Key) => page.locator(`section#${key.replaceAll('_', '-')}`);
// The plot's own SVG is also exposed as an image, so the wrapper is the first match.
const chart = (page: Page, key: Key) => section(page, key).getByRole('img').first();
// Bars are <rect> elements, or <path> elements once a corner is rounded, so both are counted.
const BARS = ['rect', 'bar']
	.flatMap((mark) => [`svg [aria-label="${mark}"] rect`, `svg [aria-label="${mark}"] path`])
	.join(', ');

async function useTheme(page: Page, t: string) {
	await page.addInitScript((th) => {
		try {
			localStorage.setItem('theme', th);
		} catch {}
	}, t);
}

/** Open the page and wait until every chart has drawn its SVG. */
async function open(page: Page) {
	await page.goto(TRENDS);
	for (const key of CHARTS) await expect(chart(page, key).locator('svg').first()).toBeVisible();
}

/** The thing a section's note describes: its chart, or else its table or list. */
async function described(page: Page, key: Key): Promise<Locator> {
	if (CHARTS.includes(key)) return chart(page, key);
	const table = section(page, key).getByRole('table');
	return (await table.count()) ? table : section(page, key).getByRole('list').first();
}

async function noHorizontalScroll(page: Page) {
	expect(
		await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)
	).toBe(true);
}

/** The computed fill of every bar in a chart. */
async function barFills(page: Page, key: Key): Promise<string[]> {
	return chart(page, key)
		.locator(BARS)
		.evaluateAll((bars) => bars.map((b) => getComputedStyle(b).fill));
}

/** --chart-1 to --chart-6 in the theme now in effect, as the browser computes them. */
async function chartTokens(page: Page): Promise<string[]> {
	return page.evaluate(() => {
		const probe = document.createElement('span');
		document.body.append(probe);
		const out = [1, 2, 3, 4, 5, 6].map((n) => {
			probe.style.color = `var(--chart-${n})`;
			return getComputedStyle(probe).color;
		});
		probe.remove();
		return out;
	});
}

// ---------------------------------------------------------------------------

test('all six sections render, each with its note beneath what it describes', async ({ page }) => {
	await open(page);
	expect(KEYS).toHaveLength(6);
	for (const key of KEYS) {
		const s = section(page, key);
		await expect(s.getByRole('heading', { level: 2 }), key).toBeVisible();
		const note = s.getByText(trends.notes[key], { exact: true });
		await expect(note, key).toBeVisible();
		const body = (await (await described(page, key)).boundingBox())!;
		const noteBox = (await note.boundingBox())!;
		expect(body.height, key).toBeGreaterThan(0);
		expect(noteBox.y, key).toBeGreaterThanOrEqual(body.y + body.height - 1);
	}
});

test('each chart draws bars with a real size', async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 900 });
	await open(page);
	for (const key of CHARTS) {
		const svg = chart(page, key).locator('svg').first();
		const box = (await svg.boundingBox())!;
		expect(box.width, key).toBeGreaterThan(400);
		expect(box.height, key).toBeGreaterThan(100);
		const tallest = await chart(page, key)
			.locator(BARS)
			.evaluateAll((bars) => Math.max(0, ...bars.map((b) => b.getBoundingClientRect().height)));
		expect(tallest, key).toBeGreaterThan(2);
	}
});

test("the charts redraw in the new theme's colours", async ({ page }) => {
	await useTheme(page, 'light');
	await open(page);
	const before = await barFills(page, 'kev_monthly');
	expect((await chartTokens(page)).some((t) => before.includes(t))).toBe(true);

	await page.getByRole('button', { name: /theme/i }).click();
	await page.getByRole('menuitemradio', { name: /apt/i }).click();
	await expect(page.locator('html')).toHaveAttribute('data-theme', 'apt');

	const tokens = await chartTokens(page);
	await expect.poll(() => barFills(page, 'kev_monthly')).not.toEqual(before);
	for (const key of CHARTS) {
		const fills = new Set(await barFills(page, key));
		expect(fills.size, key).toBeGreaterThan(0);
		for (const fill of fills) expect(tokens, `${key} ${fill}`).toContain(fill);
	}
});

test('no time axis starts before the trends window', async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 900 });
	await open(page);
	const startYear = Number(trends.window_start.slice(0, 4));
	const figures = page.locator('figure[data-x="time"]');
	expect(await figures.count()).toBeGreaterThanOrEqual(2);
	for (const figure of await figures.all()) {
		const labels = figure.locator('svg [aria-label="x-axis tick label"] text');
		const texts = await labels.allTextContents();
		expect(texts.length).toBeGreaterThan(0);
		// Every labelled year is inside the window, and the first tick carries one.
		const years = texts.map((t) => /\d{4}/.exec(t)?.[0]).filter(Boolean).map(Number);
		expect(/\d{4}/.test(texts[0])).toBe(true);
		expect(Math.min(...years)).toBeGreaterThanOrEqual(startYear);

		// The first tick is the window start and sits at the left end of the
		// baseline, so nothing is drawn to its left.
		const firstTick = await labels.first().evaluate((el) => {
			const r = el.getBoundingClientRect();
			return r.left + r.width / 2;
		});
		const left = await figure
			.locator(`${BARS}, svg [aria-label="rule"] line`)
			.evaluateAll((els) => Math.min(...els.map((e) => e.getBoundingClientRect().left)));
		expect(left).toBeGreaterThanOrEqual(firstTick - 1.5);
	}
});

for (const t of themes) {
	test(`at 375px in ${t} nothing scrolls sideways and every chart fits`, async ({ page }) => {
		await page.setViewportSize({ width: 375, height: 800 });
		await useTheme(page, t);
		await open(page);
		await noHorizontalScroll(page);
		for (const key of CHARTS) {
			const box = (await chart(page, key).locator('svg').first().boundingBox())!;
			expect(box.x, key).toBeGreaterThanOrEqual(0);
			expect(box.x + box.width, key).toBeLessThanOrEqual(375);
		}
	});
}

test('at 375px the source table scrolls in its own box instead of breaking words', async ({ page }) => {
	await page.setViewportSize({ width: 375, height: 800 });
	await open(page);
	const table = section(page, 'source_health').getByRole('table');
	// A name, date or status split into fragments ("Septem / ber", "CUR / REN / T")
	// is unreadable, so a row is never taller than a two-line name.
	const heights = await table
		.locator('tbody tr')
		.evaluateAll((rows) => rows.map((r) => r.getBoundingClientRect().height));
	expect(Math.max(...heights)).toBeLessThan(72);
	await noHorizontalScroll(page);
});

test('a chart redraws to the new width when the window narrows', async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 900 });
	await open(page);
	const svg = chart(page, 'kev_monthly').locator('svg').first();
	expect((await svg.boundingBox())!.width).toBeGreaterThan(600);
	await page.setViewportSize({ width: 375, height: 800 });
	await expect.poll(async () => (await svg.boundingBox())!.width).toBeLessThanOrEqual(343);
});

test('reporting activity shows the most reported actors by name', async ({ page }) => {
	await open(page);
	const totals = new Map<string, number>();
	for (const r of trends.reporting_activity) {
		if (r.quarter >= '2024-Q1') totals.set(r.actor, (totals.get(r.actor) ?? 0) + r.count);
	}
	const top = [...totals].sort((a, b) => b[1] - a[1])[0][0];
	await expect(chart(page, 'reporting_activity').locator('svg text', { hasText: nameOf(top) })).toHaveCount(1);
});

test('the tables list every KEV link and every source', async ({ page }) => {
	await open(page);
	const links = section(page, 'kev_actor_links').getByRole('table');
	for (const l of trends.kev_actor_links) {
		const row = links.getByRole('row').filter({ hasText: l.cve });
		for (const id of l.actors) await expect(row).toContainText(nameOf(id));
	}
	const health = section(page, 'source_health').getByRole('table');
	await expect(health.getByRole('row')).toHaveCount(trends.source_health.length + 1);
	for (const s of trends.source_health) {
		const row = health.getByRole('row').filter({ hasText: sourceLabel(s.name).name });
		await expect(row).toContainText(s.stale ? 'Stale' : 'Current');
	}
});

test('newly documented actors are listed with their first date and basis', async ({ page }) => {
	await open(page);
	const list = section(page, 'new_actors').getByRole('list').first();
	for (const a of trends.new_actors) {
		const item = list.getByRole('listitem').filter({ hasText: nameOf(a.actor) });
		await expect(item.locator(`time[datetime="${a.first_seen}"]`)).toBeVisible();
	}
});

test('with scripts blocked, the headings, notes and tables still read', async ({ page }) => {
	await page.route('**/*.js', (r) => r.abort());
	await page.goto(TRENDS);
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Trends');
	for (const key of KEYS) await expect(section(page, key).getByText(trends.notes[key], { exact: true })).toBeVisible();
	await expect(section(page, 'source_health').getByRole('row')).toHaveCount(trends.source_health.length + 1);
	await expect(section(page, 'kev_monthly')).toContainText(/needs scripts/i);
});

test('the trends page loads without console errors or warnings', async ({ page }) => {
	const problems: string[] = [];
	// The config blocks the service worker so page.route works, and Chromium logs a warning about
	// each blocked registration. That warning comes from the test setup, not from the page.
	const fromSetup = /Service Worker registration blocked by Playwright/;
	page.on(
		'console',
		(m) => (m.type() === 'error' || m.type() === 'warning') && !fromSetup.test(m.text()) && problems.push(m.text())
	);
	page.on('pageerror', (e) => problems.push(e.message));
	await open(page);
	await page.getByRole('button', { name: /theme/i }).click();
	await page.getByRole('menuitemradio', { name: /dark/i }).click();
	await page.waitForLoadState('networkidle');
	expect(problems).toEqual([]);
});
