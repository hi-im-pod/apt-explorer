import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { test, expect, type Locator, type Page } from '@playwright/test';
import type { ActorsIndex, Evaluation, Guess, Guesses, Term, Terms } from '../src/lib/data/types';
import { confidenceText, percentText, termCountText } from '../src/routes/guesses/view';

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
	const banner = page.locator('.intro').getByRole('note');
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

test('the page only praises the High band when the evaluation used it', async ({ page }) => {
	const ev = real.evaluation as Evaluation;
	const usesHigh = ev.bands.some((b) => b.band === 'high' && b.n > 0);
	await page.goto(PAGE);
	const note = page.locator('#evaluation .section-note');
	if (usesHigh) {
		await expect(note).toContainText('helps most where it says High');
	} else {
		await expect(note).not.toContainText('helps most');
		await expect(note).toContainText('No guess reaches the High band');
	}
	// Every refusal the evaluation records is printed among the limitations.
	for (const l of ev.limitations) await expect(page.locator('#evaluation')).toContainText(l.slice(0, 40));
});

test('each kept signal says which label it pushes toward, for both signs of weight', async ({ page }) => {
	const ev = real.evaluation as Evaluation;
	const kept = ev.signals.filter((s) => s.kept && s.weight != null && s.weight !== 0);
	const toward = (w: number) => (w > 0 ? 'malware' : 'actor');
	const pos = kept.find((s) => (s.weight ?? 0) > 0);
	const neg = kept.find((s) => (s.weight ?? 0) < 0);
	expect(pos, 'the data has a kept signal that points toward malware').toBeTruthy();
	expect(neg, 'the data has a kept signal that points toward actor').toBeTruthy();
	await page.goto(PAGE);
	for (const s of [pos!, neg!]) {
		const item = page.locator('#evaluation .signals li', { has: page.locator('code', { hasText: new RegExp(`^${s.signal}$`) }) });
		await expect(item.locator('.signal-facts')).toContainText(
			`pushes toward ${toward(s.weight!)}, strength ${Math.abs(s.weight!).toFixed(1)}`
		);
		await expect(item.locator('.signal-facts')).not.toContainText(/weight -?\d/);
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
	const items = page.locator('#guess-list .guesses .guess');
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
	const first = page.locator('#guess-list .guess', { has: page.locator('details') }).first();
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
	const items = page.locator('#guess-list .guesses .guess');
	const count = page.locator('#guess-list .count');
	await expect(count).toHaveText(`Showing ${real.guesses.length} of ${real.guesses.length}`);

	const actors = real.guesses.filter((g) => g.label === 'actor');
	await page.locator('#guess-list').getByLabel('Label').selectOption('actor');
	await expect(items).toHaveCount(actors.length);
	await expect(count).toHaveText(`Showing ${actors.length} of ${real.guesses.length}`);
	for (const text of await items.locator('.label-pill').allInnerTexts()) expect(text).toBe('Actor');

	// The measured bands decide which ones the page offers, so the test filters on a band the data
	// really uses. Hard-coding "high" broke when calibration left nobody in that band.
	const band = actors[0].band;
	const inBand = actors.filter((g) => g.band === band);
	await page.locator('#guess-list').getByLabel('Confidence').selectOption(band);
	await expect(items).toHaveCount(inBand.length);

	await page.locator('#guess-list').getByRole('searchbox', { name: 'Search' }).fill('zzzz-no-such-name');
	await expect(items).toHaveCount(0);
	await expect(page.locator('#guess-list .empty')).toContainText(/no guess matches/i);

	await page.locator('#guess-list').getByRole('button', { name: 'Clear the filters' }).click();
	await expect(items).toHaveCount(real.guesses.length);
	await expect(page.locator('#guess-list').getByLabel('Label')).toHaveValue('all');
});

test('the text filter finds a name and ignores case', async ({ page }) => {
	await page.goto(PAGE);
	const target = real.guesses[0].name;
	await page.locator('#guess-list').getByRole('searchbox', { name: 'Search' }).fill(`  ${target.toUpperCase()} `);
	const names = await page.locator('#guess-list .guess .name').allInnerTexts();
	expect(names).toContain(target);
	expect(names.every((n) => n.toLowerCase().includes(target.toLowerCase()))).toBe(true);
});

test('a matched actor links to that actor profile', async ({ page }) => {
	const body: Guesses = { evaluation: real.evaluation, guesses: synthGuesses(3) };
	await openWith(page, body);
	const link = page.locator('#guess-list .guess').first().getByRole('link', { name: index[0].name });
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
		await expect(page.locator('#guess-list .guess')).toHaveCount(0);
		await expect(page.locator('#guess-list .filters')).toHaveCount(0);
	});

	test('a measured method with nothing to guess says so', async ({ page }) => {
		await openWith(page, { evaluation: real.evaluation, guesses: [] });
		await expect(page.locator('#guess-list .empty')).toContainText(/no unresolved name needs a guess/i);
		await expect(page.locator('#guess-list .guess')).toHaveCount(0);
	});

	test('one guess reads in the singular', async ({ page }) => {
		await openWith(page, { evaluation: real.evaluation, guesses: synthGuesses(1) });
		await expect(page.locator('#guess-list .guess')).toHaveCount(1);
		await expect(page.locator('#guess-list')).toContainText('1 name resolves to no actor');
		await expect(page.locator('#guess-list .count')).toHaveText('Showing 1 of 1');
	});

	test('two hundred guesses all render, and a long unbroken name stays inside its card', async ({ page }) => {
		await page.setViewportSize({ width: 375, height: 800 });
		await openWith(page, { evaluation: real.evaluation, guesses: synthGuesses(200) });
		await expect(page.locator('#guess-list .guess')).toHaveCount(200);
		await expect(page.locator('#guess-list .count')).toHaveText('Showing 200 of 200');
		const report = await page.evaluate(() => ({
			scroll: document.documentElement.scrollWidth,
			client: document.documentElement.clientWidth
		}));
		expect(report.scroll).toBeLessThanOrEqual(report.client);
		const long = page.locator('#guess-list .guess', { hasText: 'Unbroken-Name' }).first();
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
			await expect(page.locator('#guess-list .filters')).toBeVisible();

			const report = await page.evaluate(() => {
				const clipped = [...document.querySelectorAll('main, main *')]
					.filter((e) => !e.closest('.visually-hidden') && !e.closest('.scroll'))
					.filter((e) => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'visible')
					.map((e) => `${e.tagName}.${e.className}`);
				const outside = [...document.querySelectorAll('#guess-list .guess, .banner, .filters select, .filters input, .track')]
					.filter((e) => e.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
					.map((e) => `${e.tagName}.${e.className}`);
				return { scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth, clipped, outside };
			});
			expect(report.clipped).toEqual([]);
			expect(report.outside).toEqual([]);
			expect(report.scroll).toBeLessThanOrEqual(report.client);

			// Text must be readable on what it sits on in this theme.
			const bg = await style(page.locator('body'), 'background-color');
			const card = page.locator('#guess-list .guess').first();
			// A guess is a ledger row, not a card: it sits on the page with a hairline under it.
			expect(await style(card, 'background-color')).toBe('rgba(0, 0, 0, 0)');
			expect(await style(card, 'border-bottom-width')).toBe('1px');
			expect(contrast(await style(card.locator('.name'), 'color'), bg)).toBeGreaterThanOrEqual(4.5);
			expect(contrast(await style(card.locator('.status'), 'color'), bg)).toBeGreaterThanOrEqual(4.5);
			expect(contrast(await style(card.locator('summary'), 'color'), bg)).toBeGreaterThanOrEqual(4.5);
			expect(contrast(await style(page.locator('h1'), 'color'), bg)).toBeGreaterThanOrEqual(4.5);
			// The banner is a caution: its edge is the unconfirmed amber, thick enough to see.
			const banner = page.locator('.intro .banner');
			expect(await style(banner, 'border-left-width')).toBe('6px');
			expect(contrast(await style(banner, 'border-left-color'), bg)).toBeGreaterThanOrEqual(3);

			// An unconfirmed guess wears a dashed amber outline that can be seen on this theme.
			const pill = page.locator('#guess-list .label-pill:not(.confirmed)').first();
			expect(await style(pill, 'border-top-style')).toBe('dashed');
			expect(await style(pill, 'border-top-color')).toBe(await style(banner, 'border-left-color'));
			expect(contrast(await style(pill, 'border-top-color'), bg)).toBeGreaterThanOrEqual(3);

			// A guess with a measured confidence shows it on a scale with two threshold ticks.
			const scaled = page.locator('#guess-list .guess', { has: page.locator('.conf') }).first();
			await expect(scaled.locator('.scale')).toBeVisible();
			await expect(scaled.locator('.scale .tick')).toHaveCount(2);
			await expect(scaled.locator('.scale')).toHaveAttribute('aria-hidden', 'true');

			// The evaluation tables fit the screen on their own, so no cell is cut off.
			const scrolling = await page.evaluate(() =>
				[...document.querySelectorAll('#evaluation .scroll')].filter((e) => e.scrollWidth > e.clientWidth + 1).length
			);
			expect(scrolling).toBe(0);

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
	await expect(page.locator('#guess-list .guess')).toHaveCount(real.guesses.length);
	await expect(page.locator('#evaluation .rate')).toContainText(percentText(real.evaluation!.accuracy));
	await expect(page.locator('#guess-list .filters')).toHaveCount(0);
	await expect(page.locator('.intro').getByRole('note')).toContainText('Pending confirmation');
});

test('the page loads without console errors', async ({ page }) => {
	const errors: string[] = [];
	page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
	page.on('pageerror', (e) => errors.push(e.message));
	await page.goto(PAGE);
	await page.waitForLoadState('networkidle');
	expect(errors).toEqual([]);
});

/** Terms of every shape: one matched to an actor, one undated, the rest with two years. */
function synthTerms(n: number): Terms {
	const terms = Array.from({ length: n }, (_, i): Term => {
		const guess: Guess = {
			name: `Larkspur ${String(i).padStart(3, '0')}`,
			count: n - i + 3,
			label: i % 2 === 0 ? 'malware' : 'actor',
			confidence: null,
			band: 'unvalidated',
			matched_actor_id: i === 0 ? index[0].id : null,
			matched_actor_name: i === 0 ? index[0].name : null,
			evidence: [{ signal: 'title_malware_ctx', detail: 'Titles call it a stealer.', weight: null }],
			status: 'pending confirmation'
		};
		return {
			name: guess.name,
			reports: n - i + 3,
			publishers: 2 + (i % 3),
			first_seen: i === 1 ? null : '2022-05-01',
			last_seen: i === 1 ? null : '2024-03-02',
			by_year: i === 1 ? [] : [{ year: 2022, count: 1 }, { year: 2024, count: n - i + 2 }],
			shapes: ['malware'],
			examples: [0, 1, 2].map((k) => ({
				id: `ex-${i}-${k}`,
				title: `Larkspur campaign report ${i}-${k}`,
				published: '2024-03-02',
				organisation: k === 0 ? 'Example Labs' : null,
				url: `https://pub${k}.example.org/${i}-${k}`
			})),
			guess
		};
	});
	return { min_reports: 3, min_publishers: 2, titles_read: 1234, hidden_as_not_names: 2, terms };
}

async function openWithTerms(page: Page, body: Terms) {
	await page.route('**/apt-explorer/data/terms.json', (r) =>
		r.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
	);
	await page.goto('/apt-explorer/methodology/');
	await page.getByRole('link', { name: 'The Name Guesses page' }).click();
	await expect(page).toHaveURL(/\/guesses\/$/);
}

test.describe('names seen in titles', () => {
	test('terms are listed with their counts, years, example links and the actor they may match', async ({ page }) => {
		const body = synthTerms(6);
		await openWithTerms(page, body);
		const section = page.locator('#title-terms');
		await expect(section.getByRole('heading', { level: 2 })).toHaveText('Seen in Titles');
		await expect(section.getByRole('note')).toContainText('Not actors.');
		await expect(section).toContainText('found in 1,234 titles');
		await expect(section).toContainText('2 more phrases');
		const items = section.locator('.terms .guess');
		await expect(items).toHaveCount(6);

		const first = items.first();
		await expect(first.locator('.name')).toHaveText(body.terms[0].name);
		await expect(first).toContainText(termCountText(body.terms[0]));
		await expect(first.locator('.when')).toHaveText('Seen 2022-05-01 to 2024-03-02');
		await expect(first.locator('.years')).toHaveAttribute('aria-label', /2022: 1, 2024: \d+/);
		await expect(first.locator('.years li')).toHaveCount(2);
		const link = first.getByRole('link', { name: index[0].name });
		await expect(first.locator('.match')).toContainText('Possibly the same as');
		expect(await link.evaluate((el) => new URL((el as HTMLAnchorElement).href).pathname)).toBe(
			`/apt-explorer/actors/${index[0].id}/`
		);

		// Only the first has a match. The others make no claim about any actor.
		await expect(section.locator('.match')).toHaveCount(1);

		const exampleRows = first.locator('.examples li');
		await expect(exampleRows.first()).toBeHidden();
		await first.locator('summary', { hasText: 'Example titles (3)' }).click();
		await expect(exampleRows).toHaveCount(3);
		const example = first.getByRole('link', { name: 'Larkspur campaign report 0-0' });
		await expect(example).toBeVisible();
		await expect(example).toHaveAttribute('href', 'https://pub0.example.org/0-0');
		await expect(example).toHaveAttribute('rel', 'noopener noreferrer');
		await expect(exampleRows.first()).toContainText('Example Labs, 2024-03-02');

		// An undated term says so rather than printing an empty range.
		await expect(items.nth(1).locator('.when')).toHaveText('No date');
		await expect(items.nth(1).locator('.years')).toHaveCount(0);
	});

	test('the jump link appears with the terms and leads to them', async ({ page }) => {
		await openWithTerms(page, synthTerms(3));
		const jump = page.locator('.jump').getByRole('link', { name: 'Go to the names seen in titles' });
		await expect(jump).toHaveAttribute('href', '#title-terms');
	});

	test('a long list opens at 25, widens on request, and a search finds any term', async ({ page }) => {
		await openWithTerms(page, synthTerms(60));
		const section = page.locator('#title-terms');
		const items = section.locator('.terms .guess');
		await expect(items).toHaveCount(25);
		await expect(section.locator('.count')).toHaveText('Showing 25 of 60');

		const search = section.getByRole('searchbox', { name: 'Search' });
		await search.fill('larkspur 059');
		await expect(items).toHaveCount(1);
		await expect(items.first().locator('.name')).toHaveText('Larkspur 059');
		await search.fill('zzzz-no-such');
		await expect(items).toHaveCount(0);
		await expect(section.locator('.empty')).toContainText(/no phrase matches/i);
		await search.fill('');

		await section.getByRole('button', { name: 'Show all 60' }).click();
		await expect(items).toHaveCount(60);
		await expect(section.getByRole('button', { name: /Show all/ })).toHaveCount(0);
	});

	test('the guess list above is unchanged by the terms', async ({ page }) => {
		await openWithTerms(page, synthTerms(30));
		await expect(page.locator('#guess-list .guess')).toHaveCount(real.guesses.length);
		await expect(page.locator('.intro').getByRole('note')).toContainText('Pending confirmation');
	});

	test('no terms means no section and no jump link', async ({ page }) => {
		await openWithTerms(page, { min_reports: 3, min_publishers: 2, titles_read: 0, hidden_as_not_names: 0, terms: [] });
		await expect(page.locator('#title-terms')).toHaveCount(0);
		await expect(page.locator('.jump').getByRole('link')).toHaveCount(1);
	});

	test('with scripts blocked, every term in the build is listed', async ({ page }) => {
		const built = readJson<Terms>('terms.json');
		await page.route('**/*.js', (r) => r.abort());
		await page.goto(PAGE);
		if (built.terms.length === 0) {
			await expect(page.locator('#title-terms')).toHaveCount(0);
		} else {
			await expect(page.locator('#title-terms .terms .guess')).toHaveCount(built.terms.length);
			await expect(page.locator('#title-terms .filters')).toHaveCount(0);
		}
	});

	for (const width of [1280, 375]) {
		for (const t of themes) {
			test(`at ${width}px in ${t}, the terms fit the screen and are painted`, async ({ page }) => {
				await page.setViewportSize({ width, height: 900 });
				await useTheme(page, t);
				await openWithTerms(page, synthTerms(8));
				await expect(page.locator('html')).toHaveAttribute('data-theme', t);
				const section = page.locator('#title-terms');
				const item = section.locator('.terms .guess').first();
				await item.locator('summary', { hasText: 'Example titles' }).click();
				const report = await page.evaluate(() => ({
					scroll: document.documentElement.scrollWidth,
					client: document.documentElement.clientWidth,
					outside: [...document.querySelectorAll('#title-terms .guess, #title-terms .banner, #title-terms .examples a')]
						.filter((e) => e.getBoundingClientRect().right > document.documentElement.clientWidth + 1)
						.map((e) => `${e.tagName}.${e.className}`)
				}));
				expect(report.outside).toEqual([]);
				expect(report.scroll).toBeLessThanOrEqual(report.client);
				const bg = await style(page.locator('body'), 'background-color');
				expect(contrast(await style(item.locator('.name'), 'color'), bg)).toBeGreaterThanOrEqual(4.5);
				expect(contrast(await style(item.locator('.when'), 'color'), bg)).toBeGreaterThanOrEqual(4.5);
				expect(contrast(await style(item.locator('.examples a').first(), 'color'), bg)).toBeGreaterThanOrEqual(4.5);
				// The busiest year fills its track, so the bars read as shares of it.
				const bars = item.locator('.years .ybar');
				const track = await bars.nth(1).boundingBox();
				const fill = await bars.nth(1).locator('.yfill').boundingBox();
				expect(track!.width).toBeGreaterThan(20);
				expect(fill!.width / track!.width).toBeCloseTo(1, 1);
				await section.scrollIntoViewIfNeeded();
				await page.screenshot({ path: fileURLToPath(new URL(`terms-${width}-${t}.png`, SHOTS)) });
			});
		}
	}
});
