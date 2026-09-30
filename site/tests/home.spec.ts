import { readFileSync } from 'node:fs';
import { test, expect, type Page } from '@playwright/test';
import { formatCount, formatDate } from '../src/lib/format';
import { sourceLabel } from '../src/lib/data/labels';
import { aliasGrid, numberWord, publishShort } from '../src/lib/home';
import type { Actor, Guesses, Resolution, Sources } from '../src/lib/data/types';

const readData = <T>(path: string): T =>
	JSON.parse(readFileSync(new URL(`../../data/${path}`, import.meta.url), 'utf8')) as T;
const themes = ['light', 'dark', 'apt'] as const;

const sources = readData<Sources>('sources.json');
const actor = readData<Actor>('actors/G0007.json');
const grid = aliasGrid(
	actor,
	sources.map((s) => s.name)
);

async function useTheme(page: Page, theme: (typeof themes)[number]) {
	await page.addInitScript((t) => {
		try {
			localStorage.setItem('theme', t);
		} catch {}
	}, theme);
}

test('the headline and the grid are drawn from the actor file', async ({ page }) => {
	await page.goto('/apt-explorer/');
	await expect(page.getByRole('heading', { level: 1 })).toHaveText(`One group, ${numberWord(actor.aliases.length)} names.`);

	const table = page.getByRole('table', { name: new RegExp(`^${actor.name}, as ${numberWord(grid.columns.length)} sources name it`) });
	await expect(table.getByRole('columnheader')).toHaveText([
		'Name used in reports',
		...grid.columns.map((k) => sourceLabel(k).short)
	]);
	const rows = table.locator('tbody tr');
	await expect(rows).toHaveCount(grid.rows.length);
	for (const [i, row] of grid.rows.entries()) {
		const cells = rows.nth(i).getByRole('cell');
		await expect(rows.nth(i).getByRole('rowheader')).toHaveText(row.name);
		for (const [c, key] of grid.columns.entries()) {
			await expect(cells.nth(c)).toHaveText(
				row.sources.includes(key) ? 'Lists this name' : 'Does not list this name'
			);
		}
	}
	await expect(page.getByText(`and ${actor.aliases.length - grid.rows.length} more names for this group`)).toBeVisible();
});

test('the grid shows disagreement between sources, not only agreement', async () => {
	const counts = grid.rows.map((r) => r.sources.length);
	expect(Math.max(...counts)).toBeGreaterThan(Math.min(...counts));
});

test('the search box opens Explore with the words as the q filter', async ({ page }) => {
	await page.goto('/apt-explorer/');
	await page.getByRole('searchbox', { name: /search reports/i }).fill('Fancy Bear');
	await page.getByRole('button', { name: 'Search', exact: true }).click();
	await expect(page).toHaveURL(/\/apt-explorer\/explore\/\?q=Fancy\+Bear$/);
});

test('Ways in has a link and a real count for each view', async ({ page }) => {
	const resolution = readData<Resolution>('resolution.json');
	const guesses = readData<Guesses>('guesses.json');
	await page.goto('/apt-explorer/');
	const items = page.getByRole('region', { name: 'Ways in' }).getByRole('listitem');
	const want: [string, string, string][] = [
		['Explore reports', '/apt-explorer/explore/', '\\d{4} to \\d{4}'],
		['Actors', '/apt-explorer/actors/', `${formatCount(resolution.stats.actor_count)} actors`],
		['Trends', '/apt-explorer/trends/', '24 months'],
		['Name guesses', '/apt-explorer/guesses/', `${formatCount(guesses.guesses.length)} guesses`],
		['Sources', '/apt-explorer/about/', `${sources.length} sources`]
	];
	await expect(items).toHaveCount(want.length);
	for (const [i, [name, href, count]] of want.entries()) {
		const link = items.nth(i).getByRole('link', { name, exact: true });
		expect(new URL(await link.evaluate((a) => (a as HTMLAnchorElement).href)).pathname).toBe(href);
		await expect(items.nth(i)).toContainText(new RegExp(count));
	}
});

test('the source table lists every source with its policy, terms and health', async ({ page }) => {
	await page.goto('/apt-explorer/');
	const rows = page.locator('.tbl tbody tr');
	await expect(rows).toHaveCount(sources.length);
	for (const s of sources) {
		const row = rows.filter({ has: page.getByRole('rowheader', { name: new RegExp(`^${escape(sourceLabel(s.name).name)}`) }) });
		await expect(row).toHaveCount(1);
		await expect(row).toContainText(publishShort(s.publish));
		await expect(row).toContainText(s.stale ? /stale/i : /current/i);
		await expect(row).toContainText(s.last_success ? formatDate(s.last_success) : 'never fetched');
		await expect(row.getByRole('link', { name: s.licence })).toHaveAttribute('href', s.licence_url);
	}
});

test('ORKL is described as links only, with no permission wording', async ({ page }) => {
	await page.goto('/apt-explorer/');
	const row = page.locator('.tbl tbody tr').filter({ hasText: 'ORKL' });
	await expect(row).toContainText('Links only');
	await expect(page.getByRole('main')).not.toContainText(/permission pending/i);
});

test('the home page credits the paper and links to the full credit on About', async ({ page }) => {
	for (const width of [1280, 375]) {
		await page.setViewportSize({ width, height: 800 });
		await page.goto('/apt-explorer/');
		const credit = page.locator('main .credit');
		await expect(credit).toBeVisible();
		await expect(credit).toContainText("Built on the dataset of Yuldoshkhujaev et al. (CCS '25).");
		const box = (await credit.boundingBox())!;
		expect(box.height).toBeGreaterThan(0);
		expect(box.x + box.width).toBeLessThanOrEqual(width);
		const link = credit.getByRole('link', { name: 'About has the full credit' });
		const href = new URL(await link.evaluate((a) => (a as HTMLAnchorElement).href));
		expect(href.pathname + href.hash).toBe('/apt-explorer/about/#paper-heading');
	}
});

test('a stale source is marked stale on the home page', async ({ page }) => {
	// A build with every source current has nothing stale to show, so the sources file is
	// edited on its way to the page. The home page loads it again on a client-side visit.
	await page.route('**/data/sources.json', async (route) => {
		const all = (await (await route.fetch()).json()) as Sources;
		await route.fulfill({ json: all.map((s) => (s.name === 'dfir' ? { ...s, stale: true } : s)) });
	});
	await page.goto('/apt-explorer/about/');
	await page.getByRole('link', { name: 'APT Explorer', exact: true }).click();
	const rows = page.locator('.tbl tbody tr');
	await expect(rows.filter({ hasText: 'The DFIR Report' })).toContainText(/stale/i);
	await expect(rows.filter({ hasText: 'Malpedia' })).toContainText(/current/i);
});

for (const w of [1280, 375])
	for (const t of themes) {
		test(`the home page fits and reads in ${t} at ${w}px`, async ({ page }) => {
			await page.setViewportSize({ width: w, height: 900 });
			await useTheme(page, t);
			await page.goto('/apt-explorer/');
			await expect(page.locator('html')).toHaveAttribute('data-theme', t);
			await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
			expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);

			// Every marker column is wide enough for its heading, and no grid row spills out of its card.
			const card = (await page.locator('.alias-card').boundingBox())!;
			for (const cell of await page.locator('.alias-grid thead th').all()) {
				const fits = await cell.evaluate((el) => el.scrollWidth <= el.clientWidth + 1);
				expect(fits, await cell.innerText()).toBe(true);
			}
			for (const row of await page.locator('.alias-grid tbody tr').all()) {
				const b = (await row.boundingBox())!;
				expect(b.x).toBeGreaterThanOrEqual(card.x);
				expect(b.x + b.width).toBeLessThanOrEqual(card.x + card.width + 1);
			}
			// Text is never smaller than 9px.
			const smallest = await page.evaluate(() =>
				Math.min(...[...document.querySelectorAll('main *')].filter((e) => e.childNodes.length && [...e.childNodes].some((n) => n.nodeType === 3 && n.textContent!.trim())).map((e) => parseFloat(getComputedStyle(e).fontSize)))
			);
			expect(smallest).toBeGreaterThanOrEqual(9);
		});
	}

test('every link and control on the home page shows a focus ring', async ({ page }) => {
	await page.goto('/apt-explorer/');
	const targets = page.locator('main a[href], main button, main input');
	const n = await targets.count();
	expect(n).toBeGreaterThan(10);
	for (let i = 0; i < n; i++) {
		const t = targets.nth(i);
		if (!(await t.isVisible())) continue;
		await t.focus();
		await page.keyboard.press('Shift+Tab');
		await page.keyboard.press('Tab');
		const ring = await t.evaluate((el) => {
			const own = getComputedStyle(el);
			const after = getComputedStyle(el, '::after');
			return [own, after].some((s) => s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) >= 2);
		});
		expect(ring, await t.innerText().catch(() => 'control')).toBe(true);
	}
});

test('the load animation is off when reduced motion is asked for', async ({ page }) => {
	await page.emulateMedia({ reducedMotion: 'reduce' });
	await page.goto('/apt-explorer/');
	const names = await page.evaluate(() =>
		[...document.querySelectorAll('main *')].map((e) => getComputedStyle(e).animationName).filter((n) => n !== 'none')
	);
	expect(names).toEqual([]);
});

test('with motion allowed, the page has one load animation', async ({ page }) => {
	await page.emulateMedia({ reducedMotion: 'no-preference' });
	await page.goto('/apt-explorer/');
	const names = await page.evaluate(() =>
		[...document.querySelectorAll('main *')].map((e) => getComputedStyle(e).animationName).filter((n) => n !== 'none')
	);
	expect(new Set(names).size).toBe(1);
});

function escape(s: string) {
	return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
