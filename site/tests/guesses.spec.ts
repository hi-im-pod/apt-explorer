import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { test, expect, type Locator, type Page } from '@playwright/test';
import type { ActorsIndex, Evaluation, Guess, Guesses } from '../src/lib/data/types';
import { confidenceText, percentText } from '../src/routes/guesses/view';

// The page must show what this build's data says, so the expectations are
// read from the same file the site is built from. A build without the file
// cannot render the page at all, so a missing file fails here with a reason.
const DATA = new URL('../../data/', import.meta.url);
if (!existsSync(new URL('guesses.json', DATA))) {
	throw new Error('data/guesses.json is missing: run the pipeline build, then copy the data, before the e2e tests');
}
const readJson = <T>(path: string): T => JSON.parse(readFileSync(new URL(path, DATA), 'utf8')) as T;
const real = readJson<Guesses>('guesses.json');
const index = readJson<ActorsIndex>('actors/index.json');

const PAGE = '/apt-explorer/guesses/';
const themes = ['light', 'dark', 'apt'] as const;
const SHOTS = new URL('../test-results/guesses/', import.meta.url);

async function useTheme(page: Page, t: string) {
	await page.addInitScript((th) => {
		try {
			localStorage.setItem('theme', th);
		} catch {}
	}, t);
}

/** Relative luminance and contrast, from computed rgb() strings. */
function contrast(a: string, b: string): number {
	const lum = (css: string) => {
		const [r, g, bl] = (css.match(/[\d.]+/g) ?? ['0', '0', '0']).slice(0, 3).map((v) => {
			const c = Number(v) / 255;
			return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
		});
		return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
	};
	const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
	return (hi + 0.05) / (lo + 0.05);
}

const style = (l: Locator, prop: string) => l.evaluate((el, p) => getComputedStyle(el).getPropertyValue(p), prop);

/** Guesses of every shape, with long names and every label and band. */
function synthGuesses(n: number): Guess[] {
	const labels = ['actor', 'malware', 'tool', 'not-an-entity'] as const;
	const bands = ['high', 'medium', 'low', 'unvalidated'] as const;
	return Array.from({ length: n }, (_, i) => {
		const label = labels[i % 4];
		const band = label === 'tool' || label === 'not-an-entity' ? 'unvalidated' : bands[i % 3];
		return {
			name: i % 25 === 0 ? `Unbroken-Name-With-No-Spaces-${i}-${'x'.repeat(60)}` : `Synthetic Name ${String(i).padStart(3, '0')}`,
			count: n - i,
			label,
			confidence: band === 'unvalidated' ? null : band === 'high' ? 0.9 : band === 'medium' ? 0.75 : 0.5,
			band,
			matched_actor_id: i === 0 ? index[0].id : null,
			matched_actor_name: i === 0 ? index[0].name : null,
			evidence: [
				{ signal: 'cluster_id', detail: `The name is written like a numbered cluster, number ${i}.`, weight: 1.2 },
				{ signal: 'vendor_suffix', detail: 'The name ends in a vendor naming word.', weight: -0.5 },
				{ signal: 'non_latin', detail: 'Context only.', weight: null }
			],
			status: 'pending confirmation'
		} satisfies Guess;
	});
}

/**
 * Open the page through a client-side visit, so that guesses.json can be
 * replaced. The prerendered page has the real file inlined, so a direct load
 * cannot be intercepted.
 */
async function openWith(page: Page, body: Guesses) {
	await page.route('**/apt-explorer/data/guesses.json', (r) =>
		r.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
	);
	await page.goto('/apt-explorer/methodology/');
	await page.getByRole('link', { name: 'The Name Guesses page' }).click();
	await expect(page).toHaveURL(/\/guesses\/$/);
}

test.beforeAll(() => mkdirSync(SHOTS, { recursive: true }));

test('the page says every label is pending confirmation and changes nothing else', async ({ page }) => {
	await page.goto(PAGE);
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Name Guesses');
	const banner = page.getByRole('note');
	await expect(banner).toContainText('Pending confirmation');
	await expect(banner).toContainText(/none\s+of\s+them\s+changes\s+an\s+actor,\s+an\s+alias,\s+a\s+report\s+link\s+or\s+a\s+match\s+rate/i);
	await expect(banner).toBeVisible();
});

test('the accuracy figure and its bars match the evaluation', async ({ page }) => {
	const ev = real.evaluation as Evaluation;
	await page.goto(PAGE);
	const section = page.locator('#evaluation');
	await expect(section.locator('.rate')).toContainText(percentText(ev.accuracy));
	const bars = section.locator('.accuracy li');
	await expect(bars).toHaveCount(3);
	const expected = [ev.accuracy, ev.baselines.name_only_accuracy, ev.baselines.majority_accuracy];
	for (const [i, value] of expected.entries()) {
		const track = await bars.nth(i).locator('.track').boundingBox();
		const fill = await bars.nth(i).locator('.fill').boundingBox();
		expect(track!.width).toBeGreaterThan(50);
		// The painted fill is the share of the painted track, so the bars can
		// be compared by eye.
		expect(fill!.width / track!.width).toBeCloseTo(value ?? 0, 1);
		await expect(bars.nth(i)).toContainText(percentText(value));
	}
});

test('the confidence bands, labels and confusion matrix are tables of the evaluation', async ({ page }) => {
	const ev = real.evaluation as Evaluation;
	await page.goto(PAGE);
	const tables = page.locator('#evaluation table');
	await expect(tables).toHaveCount(4);
	await expect(tables.nth(0).locator('tbody tr')).toHaveCount(ev.bands.length);
	for (const [i, b] of ev.bands.entries()) {
		const row = tables.nth(0).locator('tbody tr').nth(i);
		await expect(row).toContainText(b.band, { ignoreCase: true });
		await expect(row).toContainText(percentText(b.precision));
	}
	await expect(tables.nth(1).locator('tbody tr')).toHaveCount(ev.per_label.length);
	for (const [i, l] of ev.per_label.entries()) {
		if (!l.validated) await expect(tables.nth(1).locator('tbody tr').nth(i)).toContainText('unvalidated');
	}
	const cells = tables.nth(2).locator('tbody td');
	await expect(cells).toHaveCount(ev.confusion.labels.length ** 2);
	expect(await cells.allInnerTexts()).toEqual(ev.confusion.rows.flat().map(String));
});

test('every guess is listed, with its label, confidence and count', async ({ page }) => {
	await page.goto(PAGE);
	const items = page.locator('.guesses .guess');
	await expect(items).toHaveCount(real.guesses.length);
	for (const i of [0, real.guesses.length - 1]) {
		const g = real.guesses[i];
		await expect(items.nth(i)).toContainText(g.name);
		await expect(items.nth(i)).toContainText(confidenceText(g));
		await expect(items.nth(i)).toContainText('pending confirmation');
	}
});

test('evidence is closed until opened, then shows each sentence and weight', async ({ page }) => {
	await page.goto(PAGE);
	const first = page.locator('.guess', { has: page.locator('details') }).first();
	const g = real.guesses.find((x) => x.evidence.length > 0)!;
	const sentence = first.locator('.detail').first();
	await expect(sentence).toBeHidden();
	await first.locator('summary').click();
	await expect(sentence).toBeVisible();
	await expect(sentence).toHaveText(g.evidence[0].detail);
	await expect(first.locator('.weight').first()).toContainText(/supports the guess|argues against it|context only/);
});

test('the filters narrow the list, count what they show and can be cleared', async ({ page }) => {
	await page.goto(PAGE);
	const items = page.locator('.guesses .guess');
	const count = page.locator('.count');
	await expect(count).toHaveText(`Showing ${real.guesses.length} of ${real.guesses.length}`);

	const actors = real.guesses.filter((g) => g.label === 'actor');
	await page.getByLabel('Label').selectOption('actor');
	await expect(items).toHaveCount(actors.length);
	await expect(count).toHaveText(`Showing ${actors.length} of ${real.guesses.length}`);
	for (const text of await items.locator('.label-pill').allInnerTexts()) expect(text).toBe('Actor');

	const high = actors.filter((g) => g.band === 'high');
	await page.getByLabel('Confidence').selectOption('high');
	await expect(items).toHaveCount(high.length);

	await page.getByRole('searchbox', { name: 'Search' }).fill('zzzz-no-such-name');
	await expect(items).toHaveCount(0);
	await expect(page.locator('#guess-list .empty')).toContainText(/no guess matches/i);

	await page.getByRole('button', { name: 'Clear the filters' }).click();
	await expect(items).toHaveCount(real.guesses.length);
	await expect(page.getByLabel('Label')).toHaveValue('all');
});

test('the text filter finds a name and ignores case', async ({ page }) => {
	await page.goto(PAGE);
	const target = real.guesses[0].name;
	await page.getByRole('searchbox', { name: 'Search' }).fill(`  ${target.toUpperCase()} `);
	const names = await page.locator('.guess .name').allInnerTexts();
	expect(names).toContain(target);
	expect(names.every((n) => n.toLowerCase().includes(target.toLowerCase()))).toBe(true);
});

test('a matched actor links to that actor profile', async ({ page }) => {
	const body: Guesses = { evaluation: real.evaluation, guesses: synthGuesses(3) };
	await openWith(page, body);
	const link = page.locator('.guess').first().getByRole('link', { name: index[0].name });
	expect(await link.evaluate((el) => new URL((el as HTMLAnchorElement).href).pathname)).toBe(`/apt-explorer/actors/${index[0].id}/`);
	await link.click();
	await expect(page).toHaveURL(new RegExp(`/actors/${index[0].id}/$`));
	await expect(page.getByRole('heading', { level: 1 })).toContainText(index[0].name);
});

test('the methodology page links here', async ({ page }) => {
	await page.goto('/apt-explorer/methodology/');
	const link = page.getByRole('link', { name: 'The Name Guesses page' });
	expect(await link.evaluate((el) => new URL((el as HTMLAnchorElement).href).pathname)).toBe(PAGE);
});

test.describe('other volumes', () => {
	test('no evaluation and no guesses gives one explanation and no empty table', async ({ page }) => {
		await openWith(page, { evaluation: null, guesses: [] });
		await expect(page.locator('#evaluation .empty')).toContainText(/too few names/i);
		await expect(page.locator('#guess-list .empty')).toContainText(/method could not be measured/i);
		await expect(page.locator('table')).toHaveCount(0);
		await expect(page.locator('.guess')).toHaveCount(0);
		await expect(page.locator('.filters')).toHaveCount(0);
	});

	test('a measured method with nothing to guess says so', async ({ page }) => {
		await openWith(page, { evaluation: real.evaluation, guesses: [] });
		await expect(page.locator('#guess-list .empty')).toContainText(/no unresolved name needs a guess/i);
		await expect(page.locator('.guess')).toHaveCount(0);
	});

	test('one guess reads in the singular', async ({ page }) => {
		await openWith(page, { evaluation: real.evaluation, guesses: synthGuesses(1) });
		await expect(page.locator('.guess')).toHaveCount(1);
		await expect(page.locator('#guess-list')).toContainText('1 name resolves to no actor');
		await expect(page.locator('.count')).toHaveText('Showing 1 of 1');
	});

	test('two hundred guesses all render, and a long unbroken name stays inside its card', async ({ page }) => {
		await page.setViewportSize({ width: 375, height: 800 });
		await openWith(page, { evaluation: real.evaluation, guesses: synthGuesses(200) });
		await expect(page.locator('.guess')).toHaveCount(200);
		await expect(page.locator('.count')).toHaveText('Showing 200 of 200');
		const report = await page.evaluate(() => ({
			scroll: document.documentElement.scrollWidth,
			client: document.documentElement.clientWidth
		}));
		expect(report.scroll).toBeLessThanOrEqual(report.client);
		const long = page.locator('.guess', { hasText: 'Unbroken-Name' }).first();
		const card = await long.boundingBox();
		const name = await long.locator('.name').boundingBox();
		expect(name!.x + name!.width).toBeLessThanOrEqual(card!.x + card!.width + 1);
	});
});

for (const width of [1280, 375]) {
	for (const t of themes) {
		test(`at ${width}px in ${t}, the page fits, reads and is painted in the theme`, async ({ page }) => {
			await page.setViewportSize({ width, height: 900 });
			await useTheme(page, t);
			await page.goto(PAGE);
			await expect(page.locator('html')).toHaveAttribute('data-theme', t);
			await expect(page.locator('.filters')).toBeVisible();

			const report = await page.evaluate(() => {
				const clipped = [...document.querySelectorAll('main, main *')]
					.filter((e) => !e.closest('.visually-hidden') && !e.closest('.scroll'))
					.filter((e) => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'visible')
					.map((e) => `${e.tagName}.${e.className}`);
				const outside = [...document.querySelectorAll('.guess, .banner, .filters select, .filters input, .track')]
					.filter((e) => e.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
					.map((e) => `${e.tagName}.${e.className}`);
				return { scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth, clipped, outside };
			});
			expect(report.clipped).toEqual([]);
			expect(report.outside).toEqual([]);
			expect(report.scroll).toBeLessThanOrEqual(report.client);

			// Text must be readable on what it sits on in this theme.
			const bg = await style(page.locator('body'), 'background-color');
			const card = page.locator('.guess').first();
			const cardBg = await style(card, 'background-color');
			expect(cardBg).not.toBe(bg);
			expect(contrast(await style(card.locator('.name'), 'color'), cardBg)).toBeGreaterThanOrEqual(4.5);
			expect(contrast(await style(card.locator('.status'), 'color'), cardBg)).toBeGreaterThanOrEqual(4.5);
			expect(contrast(await style(card.locator('summary'), 'color'), cardBg)).toBeGreaterThanOrEqual(4.5);
			expect(contrast(await style(page.locator('h1'), 'color'), bg)).toBeGreaterThanOrEqual(4.5);
			// The banner is a caution: its edge is the danger colour, thick enough to see.
			const banner = page.locator('.banner');
			expect(await style(banner, 'border-left-width')).toBe('6px');
			expect(contrast(await style(banner, 'border-left-color'), await style(banner, 'background-color'))).toBeGreaterThanOrEqual(3);

			// A one-word cell stays on one line: a taller cell means the word was cut.
			// The row height cannot tell, because a long neighbour makes the row
			// tall, so count the line boxes the word itself paints.
			const cut = await page.evaluate(() =>
				[...document.querySelectorAll('#evaluation th, #evaluation td')]
					.filter((c) => {
						const text = (c.textContent ?? '').trim();
						if (text === '' || /\s/.test(text)) return false;
						const range = document.createRange();
						range.selectNodeContents(c);
						return range.getClientRects().length > 1;
					})
					.map((c) => c.textContent?.trim())
			);
			expect(cut).toEqual([]);

			// Viewport shots: a full-page capture of the list is too tall to inspect.
			const shot = (name: string) => fileURLToPath(new URL(`guesses-${width}-${t}-${name}.png`, SHOTS));
			await page.screenshot({ path: shot('top') });
			await page.locator('#guess-list').scrollIntoViewIfNeeded();
			await page.locator('#guess-list .guess').nth(3).locator('summary').click();
			await page.locator('#guess-list h2').scrollIntoViewIfNeeded();
			await page.screenshot({ path: shot('list') });
			await page.locator('#evaluation h3').nth(3).scrollIntoViewIfNeeded();
			await page.screenshot({ path: shot('tables') });
		});
	}
}

test('with scripts blocked, the whole list and the evaluation still read', async ({ page }) => {
	await page.route('**/*.js', (r) => r.abort());
	await page.goto(PAGE);
	await expect(page.locator('.guess')).toHaveCount(real.guesses.length);
	await expect(page.locator('#evaluation .rate')).toContainText(percentText(real.evaluation!.accuracy));
	await expect(page.locator('.filters')).toHaveCount(0);
	await expect(page.getByRole('note')).toContainText('Pending confirmation');
});

test('the page loads without console errors', async ({ page }) => {
	const errors: string[] = [];
	page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
	page.on('pageerror', (e) => errors.push(e.message));
	await page.goto(PAGE);
	await page.waitForLoadState('networkidle');
	expect(errors).toEqual([]);
});
