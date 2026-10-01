import { readFileSync } from 'node:fs';
import { test, expect, type Locator, type Page } from '@playwright/test';
import type { ActorsIndex, Trends, Vulns } from '../src/lib/data/types';
import { sourceLabel } from '../src/lib/data/labels';

// Expectations come from the same data/ the site is built from.
const read = <T>(path: string): T =>
	JSON.parse(readFileSync(new URL(`../../data/${path}`, import.meta.url), 'utf8')) as T;
const trends = read<Trends>('trends.json');
const actors = read<ActorsIndex>('actors/index.json');
const vulns = read<Vulns>('vulns.json');
const epssOf = (cve: string) => vulns.find((v) => v.cve === cve)?.epss ?? null;
const percentOf = (p: number) => (p < 0.001 ? 'under 0.1%' : p >= 0.9995 ? 'over 99.9%' : `${(p * 100).toFixed(1)}%`);
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
	const heatBefore = new Set(await barFills(page, 'reporting_activity'));
	expect((await chartTokens(page)).some((t) => before.includes(t))).toBe(true);

	await page.getByRole('button', { name: /theme/i }).click();
	await page.getByRole('menuitemradio', { name: /apt/i }).click();
	await expect(page.locator('html')).toHaveAttribute('data-theme', 'apt');

	const tokens = await chartTokens(page);
	await expect.poll(() => barFills(page, 'kev_monthly')).not.toEqual(before);
	for (const key of CHARTS) {
		const fills = new Set(await barFills(page, key));
		expect(fills.size, key).toBeGreaterThan(0);
		if (key === 'reporting_activity') {
			// Heatmap cells are blends of two theme colours, so no cell is a bare token. None may keep the old theme's colour.
			for (const fill of fills) expect(heatBefore.has(fill), `${key} ${fill}`).toBe(false);
			continue;
		}
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
		const heatmap = await figure.evaluate((f) => !!f.closest('section#reporting-activity'));
		if (heatmap) {
			// A grid labels each column at its middle, so the first tick is inside the first column.
			const first = await figure.locator(BARS).first().evaluate((el) => {
				const r = el.getBoundingClientRect();
				return { left: r.left, right: r.right };
			});
			expect(firstTick).toBeGreaterThanOrEqual(first.left);
			expect(firstTick).toBeLessThanOrEqual(first.right);
		} else {
			expect(left).toBeGreaterThanOrEqual(firstTick - 1.5);
		}
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

for (const t of themes) {
	test(`in ${t} every count in the activity heatmap has one colour and reads against its cell`, async ({ page }) => {
		await useTheme(page, t);
		await open(page);
		const painted = await chart(page, 'reporting_activity').evaluate((root) => {
			const rgb = (v: string) => (v.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
			const cells = [...root.querySelectorAll('[aria-label="bar"] rect, [aria-label="bar"] path')]
				.map((el) => getComputedStyle(el))
				.filter((st) => Number(st.fillOpacity) === 1)
				.map((st) => rgb(st.fill));
			const counts = [...root.querySelectorAll('text')]
				.filter((el) => /^[\d,]+$/.test(el.textContent ?? ''))
				.map((el) => rgb(getComputedStyle(el).fill));
			return { cells, counts };
		});
		expect(painted.counts.length).toBeGreaterThan(0);
		expect(painted.counts.length).toBe(painted.cells.length);
		expect(new Set(painted.counts.map((c) => c.join(','))).size).toBe(1);
		const lum = ([r, g, b]: number[]) => {
			const lin = (c: number) => ((c / 255) <= 0.03928 ? c / 255 / 12.92 : ((c / 255 + 0.055) / 1.055) ** 2.4);
			return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
		};
		const ratio = (a: number[], b: number[]) => {
			const [x, y] = [lum(a), lum(b)];
			return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
		};
		for (const [i, cell] of painted.cells.entries()) {
			expect(ratio(painted.counts[i], cell), `cell ${i}`).toBeGreaterThanOrEqual(4.5);
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

// ---------------------------------------------------------------------------
// Legibility. Each check reads what the browser painted: where every tick label
// sits, how big it is, and what colour it is against the page.

interface LabelBox {
	text: string;
	left: number;
	right: number;
	top: number;
	bottom: number;
	size: number;
	contrast: number;
}

/** Every tick label under a figure's SVG, with its painted box, size and contrast on the page. */
async function tickLabels(figure: Locator, axis: 'x' | 'y'): Promise<{ svg: DOMRect; labels: LabelBox[] }> {
	return figure.locator('svg').first().evaluate((svg, ax) => {
		// A computed colour may be in any CSS colour syntax, so a canvas turns it into RGB.
		const ctx = document.createElement('canvas').getContext('2d')!;
		const rgb = (css: string): [number, number, number] => {
			ctx.clearRect(0, 0, 1, 1);
			ctx.fillStyle = '#000';
			ctx.fillStyle = css;
			ctx.fillRect(0, 0, 1, 1);
			const d = ctx.getImageData(0, 0, 1, 1).data;
			return [d[0], d[1], d[2]];
		};
		const lum = ([r, g, b]: number[]) => {
			const f = (v: number) => ((v /= 255) <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
			return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
		};
		const bg = rgb(getComputedStyle(document.body).backgroundColor);
		const texts = [...svg.querySelectorAll(`[aria-label="${ax}-axis tick label"] text`)];
		return {
			svg: svg.getBoundingClientRect().toJSON(),
			labels: texts.map((t) => {
				const r = t.getBoundingClientRect();
				const s = getComputedStyle(t);
				const a = lum(rgb(s.fill));
				const b = lum(bg);
				return {
					text: t.textContent ?? '',
					left: r.left,
					right: r.right,
					top: r.top,
					bottom: r.bottom,
					size: parseFloat(s.fontSize),
					contrast: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
				};
			})
		};
	}, axis);
}

const FIGURES: { key: Key; scope: string; axis: 'time' | 'value' }[] = [
	{ key: 'reporting_activity', scope: 'section#reporting-activity figure', axis: 'time' },
	{ key: 'new_actors', scope: 'section#new-actors figure', axis: 'time' },
	{ key: 'kev_monthly', scope: 'section#kev-monthly figure', axis: 'time' },
	{ key: 'reported_vs_documented', scope: 'section#reported-vs-documented figure', axis: 'value' }
];

for (const vp of [
	{ name: '1280', width: 1280, height: 900 },
	{ name: '375', width: 375, height: 800 }
]) {
	for (const t of themes) {
		test(`at ${vp.name}px in ${t} every chart has readable, separate tick labels inside its box`, async ({ page }) => {
			await page.setViewportSize({ width: vp.width, height: vp.height });
			await useTheme(page, t);
			await open(page);
			for (const f of FIGURES) {
				const figure = page.locator(f.scope);
				// The new-actors chart is drawn only when the actors spread over two months.
				if (!(await figure.count())) {
					expect(f.key).toBe('new_actors');
					continue;
				}
				await expect(figure.locator('svg').first()).toBeVisible();
				for (const axis of ['x', 'y'] as const) {
					if (axis === 'y' && f.axis === 'value') continue;
					const { svg, labels } = await tickLabels(figure, axis);
					const where = `${f.key} ${axis} axis`;
					// Facets and bars share an x axis, so the y axis may be empty only for the small multiples.
					if (axis === 'y' && labels.length === 0) continue;
					expect(labels.length, where).toBeGreaterThanOrEqual(axis === 'x' ? 3 : 1);
					for (const l of labels) {
						expect(l.text.trim().length, where).toBeGreaterThan(0);
						// Painted inside the chart's own box, so nothing is cut off at an edge.
						expect(l.left, `${where} "${l.text}" left`).toBeGreaterThanOrEqual(svg.left - 0.5);
						expect(l.right, `${where} "${l.text}" right`).toBeLessThanOrEqual(svg.right + 0.5);
						expect(l.top, `${where} "${l.text}" top`).toBeGreaterThanOrEqual(svg.top - 0.5);
						expect(l.bottom, `${where} "${l.text}" bottom`).toBeLessThanOrEqual(svg.bottom + 0.5);
						expect(l.size, `${where} "${l.text}" size`).toBeGreaterThanOrEqual(11);
						expect(l.contrast, `${where} "${l.text}" contrast`).toBeGreaterThanOrEqual(4.5);
					}
					if (axis === 'x') {
						// Neighbouring labels do not touch, whatever the width.
						const sorted = [...labels].sort((a, b) => a.left - b.left);
						for (let i = 1; i < sorted.length; i++) {
							expect(
								sorted[i].left - sorted[i - 1].right,
								`${where} "${sorted[i - 1].text}" and "${sorted[i].text}"`
							).toBeGreaterThanOrEqual(2);
						}
					}
				}
			}
		});

		test(`at ${vp.name}px in ${t} charts are tall enough and multi-series charts name their series`, async ({ page }) => {
			await page.setViewportSize({ width: vp.width, height: vp.height });
			await useTheme(page, t);
			await open(page);
			const tokens = await chartTokens(page);
			const heights: Record<string, number> = {
				reporting_activity: 6 * 40,
				kev_monthly: 240,
				reported_vs_documented: 40 * 5
			};
			for (const [key, min] of Object.entries(heights)) {
				const box = (await chart(page, key as Key).locator('svg').first().boundingBox())!;
				expect(box.height, key).toBeGreaterThanOrEqual(min);
			}
			// A legend swatch that is painted in a series colour, next to its label.
			for (const key of CHARTS) {
				const legend = section(page, key).locator('.legend li');
				// The heatmap has one scale, so one legend item; the other charts name two series.
				expect(await legend.count(), key).toBeGreaterThanOrEqual(key === 'reporting_activity' ? 1 : 2);
				const text = await section(page, key).locator('.legend').innerText();
				expect(text.length, key).toBeGreaterThan(5);
				const colours = await legend.locator('.key').evaluateAll((els) =>
					els.map((e) => {
						const r = e.getBoundingClientRect();
						return { w: r.width, h: r.height, bg: getComputedStyle(e).backgroundColor };
					})
				);
				for (const c of colours) {
					expect(c.w, key).toBeGreaterThan(0);
					expect(c.h, key).toBeGreaterThan(0);
				}
				const distinct = new Set(colours.map((c) => c.bg));
				expect(distinct.size, `${key} swatches differ`).toBe(colours.length);
				// At least one swatch is the chart's own series colour.
				const seriesColours = colours.filter((c) => tokens.includes(c.bg));
				expect(seriesColours.length, key).toBeGreaterThanOrEqual(1);
			}
		});
	}
}

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

/** Every row of the paginated KEV table, read one page at a time. */
async function kevRows(page: Page): Promise<string[]> {
	const box = section(page, 'kev_actor_links');
	await box.getByLabel('Rows per page').selectOption('100');
	const next = box.getByRole('button', { name: 'Next' }).first();
	const rows: string[] = [];
	for (;;) {
		// textContent, not innerText: names folded into a closed disclosure are still in the page.
		rows.push(...(await box.getByRole('row').evaluateAll((els) => els.map((e) => e.textContent ?? ''))));
		if (await next.isDisabled()) break;
		await next.click();
	}
	return rows;
}

test('the KEV table lists every link, and every source is in the source table', async ({ page }) => {
	await open(page);
	const rows = await kevRows(page);
	for (const l of trends.kev_actor_links) {
		const row = rows.find((r) => r.includes(l.cve));
		expect(row, l.cve).toBeTruthy();
		for (const id of l.actors) expect(row, `${l.cve} ${id}`).toContain(nameOf(id));
	}
	const health = section(page, 'source_health').getByRole('table');
	await expect(health.getByRole('row')).toHaveCount(trends.source_health.length + 1);
	for (const s of trends.source_health) {
		const row = health.getByRole('row').filter({ hasText: sourceLabel(s.name).name });
		await expect(row).toContainText(s.stale ? 'Stale' : 'Current');
	}
});

for (const vp of [
	{ name: 375, width: 375, height: 800 },
	{ name: 1280, width: 1280, height: 900 }
]) {
	test(`at ${vp.name}px the KEV table is paged, has no sideways scroll, and links each CVE to the explorer`, async ({
		page
	}) => {
		await page.setViewportSize({ width: vp.width, height: vp.height });
		await open(page);
		const box = section(page, 'kev_actor_links');
		await expect(box.getByText(`Rows 1 to 25 of ${trends.kev_actor_links.length}`, { exact: true })).toBeVisible();
		await expect(box.getByRole('row')).toHaveCount(26);
		await noHorizontalScroll(page);
		const frame = (await box.locator('.frame').boundingBox())!;
		for (const chip of await box.locator('li').all()) {
			const r = await chip.boundingBox();
			if (!r) continue; // inside a closed disclosure
			expect(r.x + r.width, 'a chip stays inside the table frame').toBeLessThanOrEqual(frame.x + frame.width + 1);
		}
		const link = box.getByRole('link').first();
		const cve = (await link.innerText()).trim();
		expect(trends.kev_actor_links.some((l) => l.cve === cve)).toBe(true);
		await expect(link).toHaveAttribute('href', `/apt-explorer/explore/?cve=${cve}`);
	});
}

test('each KEV row shows its EPSS score, and the sort puts the highest score first', async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 900 });
	await open(page);
	const box = section(page, 'kev_actor_links');
	await expect(box.getByRole('columnheader', { name: /EPSS/ })).toBeVisible();
	const first = box.getByRole('row').nth(1);
	const cve = (await first.getByRole('link').innerText()).trim();
	const score = epssOf(cve);
	if (score === null) await expect(first).toContainText('Not scored');
	else await expect(first).toContainText(percentOf(score));

	await box.getByLabel('Sort by').selectOption('epss');
	await expect(box.getByText(`Rows 1 to 25 of ${trends.kev_actor_links.length}`, { exact: true })).toBeVisible();
	const top = trends.kev_actor_links.map((l) => epssOf(l.cve) ?? -1).sort((a, b) => b - a)[0];
	const sortedFirst = (await box.getByRole('row').nth(1).getByRole('link').innerText()).trim();
	expect(epssOf(sortedFirst)).toBe(top);
	await noHorizontalScroll(page);
});

test('at 375px the EPSS score reads as a sentence and the table does not scroll sideways', async ({ page }) => {
	await page.setViewportSize({ width: 375, height: 800 });
	await open(page);
	const box = section(page, 'kev_actor_links');
	await expect(box.getByText(/chance of exploitation in the next 30 days/).first()).toBeVisible();
	await noHorizontalScroll(page);
});

test('a CVE with many actors folds the extra names into a native disclosure that holds every name', async ({ page }) => {
	await open(page);
	const many = trends.kev_actor_links.reduce((a, b) => (b.actors.length > a.actors.length ? b : a));
	expect(many.actors.length).toBeGreaterThan(4);
	const box = section(page, 'kev_actor_links');
	await box.getByLabel('Rows per page').selectOption('100');
	const next = box.getByRole('button', { name: 'Next' }).first();
	let row = box.getByRole('row').filter({ hasText: many.cve });
	while ((await row.count()) === 0) {
		await next.click();
		row = box.getByRole('row').filter({ hasText: many.cve });
	}
	const more = row.locator('summary');
	await expect(more).toHaveText(`${many.actors.length - 4} more`);
	await more.click();
	for (const id of many.actors) await expect(row).toContainText(nameOf(id));
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

// A tooltip must stay inside the chart's own box, at the narrowest and widest layouts.
for (const vp of [
	{ name: 375, width: 375, height: 800 },
	{ name: 1280, width: 1280, height: 900 }
]) {
	for (const key of CHARTS) {
		test(`at ${vp.name}px the ${key} tooltip stays inside its chart at every sampled point`, async ({ page }) => {
			await page.setViewportSize({ width: vp.width, height: vp.height });
			await open(page);
			const holder = section(page, key).locator('svg').first();
			await holder.scrollIntoViewIfNeeded();
			const svg = (await holder.boundingBox())!;
			const tip = section(page, key).locator('[data-chart-tip]');
			let shown = 0;
			// A grid of points across the chart, including both edges where a tip is most likely to spill.
			for (const fy of [0.15, 0.5, 0.85]) {
				for (const fx of [0.03, 0.2, 0.5, 0.8, 0.97]) {
					await page.mouse.move(svg.x + svg.width * fx, svg.y + svg.height * fy);
					if (!(await tip.isVisible())) continue;
					shown++;
					const t = (await tip.boundingBox())!;
					const where = `${key} at ${fx},${fy}`;
					expect(t.x, where).toBeGreaterThanOrEqual(svg.x - 1);
					expect(t.x + t.width, where).toBeLessThanOrEqual(svg.x + svg.width + 1);
					expect(t.y, where).toBeGreaterThanOrEqual(svg.y - 1);
					expect(t.y + t.height, where).toBeLessThanOrEqual(svg.y + svg.height + 1);
					expect(t.width, `${where} is not wider than 260px`).toBeLessThanOrEqual(261);
				}
			}
			expect(shown, `${key} showed a tooltip somewhere`).toBeGreaterThan(0);
		});
	}
}

test('the technique tooltip gives counts and no technique IDs', async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 900 });
	await open(page);
	const holder = section(page, 'reported_vs_documented').locator('svg').first();
	await holder.scrollIntoViewIfNeeded();
	const svg = (await holder.boundingBox())!;
	await page.mouse.move(svg.x + svg.width * 0.3, svg.y + 30);
	const tip = section(page, 'reported_vs_documented').locator('[data-chart-tip]');
	await expect(tip).toBeVisible();
	const text = await tip.innerText();
	expect(text).toMatch(/technique/);
	expect(text).not.toMatch(/T\d{4}/);
	expect((await tip.boundingBox())!.height).toBeLessThan(120);
});

test('a tap shows a tooltip, stays after the finger lifts, and a tap elsewhere closes it', async ({ browser }) => {
	const ctx = await browser.newContext({ viewport: { width: 375, height: 800 }, hasTouch: true, isMobile: true });
	const page = await ctx.newPage();
	await open(page);
	const holder = section(page, 'kev_monthly').locator('svg').first();
	await holder.scrollIntoViewIfNeeded();
	const svg = (await holder.boundingBox())!;
	const tip = section(page, 'kev_monthly').locator('[data-chart-tip]');
	await page.touchscreen.tap(svg.x + svg.width * 0.6, svg.y + svg.height * 0.6);
	await expect(tip).toBeVisible();
	await page.waitForTimeout(300);
	await expect(tip).toBeVisible();
	await page.touchscreen.tap(svg.x + 4, svg.y - 6 > 0 ? svg.y - 6 : svg.y + svg.height + 6);
	await expect(tip).toBeHidden();
	await ctx.close();
});
