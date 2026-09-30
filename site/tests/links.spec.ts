import { test, expect, type Page } from '@playwright/test';
import type { Report } from '../src/lib/data/types';
import { LINK_KINDS, describeLinks } from '../src/lib/links';
import { SHARD, reports } from './explore-data';

// The panel must tell an original publisher link from a copy
// (an archive or a mirror). These checks read what is painted, at both widths
// and in all three themes, because a label that exists in the DOM but is
// clipped or invisible does not tell a visitor anything.

const EXPLORE = '/apt-explorer/explore/';
const themes = ['light', 'dark', 'apt'] as const;
const viewports = [
	{ name: '1280', width: 1280, height: 900 },
	{ name: '375', width: 375, height: 800 }
] as const;

// Rows are found in the data by the situation the helper reports, so a rebuild
// with different reports does not break the tests. A title of plain words that
// occurs once is chosen so the table can be searched for the row.
const titleCount = new Map<string, number>();
for (const r of reports) titleCount.set(r.title, (titleCount.get(r.title) ?? 0) + 1);
const findable = (r: Report) => titleCount.get(r.title) === 1 && /^[A-Za-z0-9 ,.:'()-]{12,80}$/.test(r.title);
const pick = (what: string, match: (r: Report) => boolean) => {
	const r = reports.find((x) => findable(x) && match(x));
	if (!r) throw new Error(`the data has no ${what}`);
	return r;
};
const situation = (r: Report) => describeLinks(r).situation;
const BOTH = pick('report with an original and a copy', (r) => situation(r) === 'both' && r.url_ok !== false);
const ONE = pick('report with an original and no copy', (r) => situation(r) === 'original-only' && r.url_ok !== false);
const VX_MIRROR = pick(
	'report whose only links are the VX-Underground mirror and ORKL copy',
	(r) => describeLinks(r).links.map((l) => l.class.kind).join() === 'vxug-mirror,orkl-archive'
);
// The data has no report with one mirror link and nothing else in a findable form, so the
// lone-mirror wording is checked on a real row with its archive link removed on the way in.
const LONE = VX_MIRROR;

async function useTheme(page: Page, t: string) {
	await page.addInitScript((th) => {
		try {
			localStorage.setItem('theme', th);
		} catch {}
	}, t);
}

async function editReport(page: Page, id: string, patch: Partial<Report>) {
	// Only the year shards hold a report's links; the index in the same folder has another shape.
	await page.route(SHARD, async (route) => {
		const shard = (await (await route.fetch()).json()) as Report[];
		await route.fulfill({ json: shard.map((r) => (r.id === id ? { ...r, ...patch } : r)) });
	});
}

const panel = (page: Page) => page.getByRole('dialog');

async function openPanel(page: Page, id: string) {
	await page.goto(`${EXPLORE}?report=${encodeURIComponent(id)}`);
	await expect(panel(page).getByRole('heading', { level: 2 })).toBeVisible({ timeout: 30_000 });
}

/** The link list is inside the panel, and each entry is painted inside the panel's box. */
async function expectInsidePanel(page: Page, selector: string) {
	const box = await panel(page).boundingBox();
	expect(box).not.toBeNull();
	const items = panel(page).locator(selector);
	const n = await items.count();
	expect(n).toBeGreaterThan(0);
	for (let i = 0; i < n; i++) {
		const b = await items.nth(i).boundingBox();
		expect(b, `${selector} ${i} is painted`).not.toBeNull();
		expect(b!.width).toBeGreaterThan(0);
		expect(b!.height).toBeGreaterThan(0);
		expect(b!.x).toBeGreaterThanOrEqual(box!.x - 1);
		expect(b!.x + b!.width).toBeLessThanOrEqual(box!.x + box!.width + 1);
	}
}

for (const vp of viewports) {
	for (const theme of themes) {
		test.describe(`${vp.name}px, ${theme} theme`, () => {
			test.use({ viewport: { width: vp.width, height: vp.height } });
			test.beforeEach(async ({ page }) => useTheme(page, theme));

			test('the panel labels an original and a copy, and explains the difference', async ({ page }) => {
				await openPanel(page, BOTH.id);
				const d = describeLinks(BOTH);
				const list = panel(page).getByRole('list', { name: /links/i });
				const links = list.getByRole('link');
				await expect(links).toHaveCount(2);
				await expect(links.nth(0)).toHaveText('Original publisher');
				await expect(links.nth(0)).toHaveAttribute('href', BOTH.url!);
				await expect(links.nth(1)).toHaveText(d.links[1].class.label);
				await expect(links.nth(1)).toHaveAttribute('href', BOTH.archive_url!);
				// The one-line difference is visible text in the panel, not a tooltip.
				const note = panel(page).locator('.note');
				await expect(note).toBeVisible();
				await expect(note).toHaveText(d.note);
				await expectInsidePanel(page, '.links li');
				await expectInsidePanel(page, '.note');
				// Each link says what it is in visible words.
				for (const l of d.links) await expect(list).toContainText(l.class.explanation);
				// The note is readable: dark text on its own surface is not the page background colour.
				const colours = await note.evaluate((el) => {
					const s = getComputedStyle(el);
					return { color: s.color, size: parseFloat(s.fontSize) };
				});
				expect(colours.size).toBeGreaterThanOrEqual(14);
				expect(colours.color).not.toBe('rgba(0, 0, 0, 0)');
			});

			test('the panel shows one labelled link when only one exists', async ({ page }) => {
				await openPanel(page, ONE.id);
				const links = panel(page).getByRole('list', { name: /links/i }).getByRole('link');
				await expect(links).toHaveCount(1);
				await expect(links.first()).toHaveText('Original publisher');
				await expect(links.first()).toHaveAttribute('href', ONE.url!);
				await expect(panel(page).locator('.note')).toHaveText(/only the original publisher link is known/i);
				await expectInsidePanel(page, '.links li');
			});

			test('a mirror is never labelled as the original and the panel says no original is known', async ({ page }) => {
				await editReport(page, LONE.id, { archive_url: null });
				await openPanel(page, LONE.id);
				const links = panel(page).getByRole('list', { name: /links/i }).getByRole('link');
				await expect(links).toHaveCount(1);
				await expect(links.first()).toHaveText('Mirror on VX-Underground');
				await expect(links.first()).toHaveAttribute('href', LONE.url!);
				await expect(panel(page)).not.toContainText('Original publisher');
				await expect(panel(page).locator('.note')).toHaveText(
					'No original publisher link is known; this is a mirror.'
				);
				await expectInsidePanel(page, '.note');
			});

			test('a mirror plus the ORKL copy lists two copies and no original', async ({ page }) => {
				await openPanel(page, VX_MIRROR.id);
				const links = panel(page).getByRole('list', { name: /links/i }).getByRole('link');
				await expect(links).toHaveCount(2);
				await expect(links.nth(0)).toHaveText('Mirror on VX-Underground');
				await expect(links.nth(1)).toHaveText('Archived copy on ORKL');
				await expect(panel(page)).not.toContainText('Original publisher');
				await expect(panel(page).locator('.note')).toContainText(/no original publisher link is known/i);
			});
		});
	}
}

const APT_MAP = 'https://lngt-apt-study-map.vercel.app/';
const APT_MAP_BACKEND = 'https://github.com/SecAI-Lab/APTMap-backend';
const APT_MAP_PAPER_REPO = 'https://github.com/SecAI-Lab/A-Decade-long-Landscape-of-Advanced-Persistent-Threats';

for (const vp of viewports) {
	for (const theme of themes) {
		test.describe(`About and Methodology at ${vp.name}px, ${theme} theme`, () => {
			test.use({ viewport: { width: vp.width, height: vp.height } });
			test.beforeEach(async ({ page }) => useTheme(page, theme));

			test('About credits APT Map with its three links, after the paper credit', async ({ page }) => {
				await page.goto('/apt-explorer/about/');
				const section = page.locator('#related-work');
				await expect(section.getByRole('heading', { level: 2 })).toHaveText('Related Work: APT Map');
				await expect(section).toBeVisible();
				for (const href of [APT_MAP, APT_MAP_BACKEND, APT_MAP_PAPER_REPO]) {
					const link = section.locator(`a[href="${href}"]`).first();
					await expect(link, href).toBeVisible();
					const box = (await link.boundingBox())!;
					expect(box.x + box.width, `${href} stays inside the viewport`).toBeLessThanOrEqual(vp.width + 1);
				}
				// It says in plain words what the map is and how this site differs.
				await expect(section).toContainText('hand-curated');
				await expect(section).toContainText('victim');
				await expect(section).toContainText('GitHub pull request');
				await expect(section).toContainText('rebuilt from open sources');
				// It claims nothing about a licence, approval or plans to contribute.
				const text = (await section.innerText()).toLowerCase();
				for (const word of ['licen', 'approv', 'endors', 'permission', 'contribut']) {
					expect(text, word).not.toContain(word);
				}
				// The paper credit stays first and stays a visible section.
				const paper = (await page.locator('#paper').boundingBox())!;
				const related = (await section.boundingBox())!;
				expect(paper.y).toBeLessThan(related.y);
				await expect(page.locator('#paper')).toBeVisible();
				// No horizontal scroll from long repository names.
				expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
			});

			test('About explains original, archive and mirror labels from the helper list', async ({ page }) => {
				await page.goto('/apt-explorer/about/');
				const section = page.locator('#report-links');
				await expect(section).toBeVisible();
				const items = section.locator('dl.kinds > div');
				await expect(items).toHaveCount(LINK_KINDS.length);
				for (const k of LINK_KINDS) {
					const item = section.locator(`[data-kind="${k.kind}"]`);
					await expect(item.locator('dt')).toHaveText(k.label);
					await expect(item.locator('dd')).toHaveText(k.explanation);
				}
				await expect(section).toContainText('no original publisher link is known');
				expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
			});

			test('Methodology gives the rule for report links, and the panel links to it', async ({ page }) => {
				await page.goto('/apt-explorer/methodology/');
				const section = page.locator('#report-links');
				await expect(section.getByRole('heading', { level: 2 })).toHaveText('Report Links');
				await expect(section).toBeVisible();
				await expect(section).toContainText('host alone');
				await expect(section).toContainText('never labelled as the original');
				await expect(section).toContainText('does not confirm that the host is the publisher');
				expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
				await openPanel(page, BOTH.id);
				await panel(page).getByRole('link', { name: /originals, archives and mirrors/i }).click();
				await expect(page).toHaveURL(/\/methodology\/#report-links$/);
				await expect(page.locator('#report-links')).toBeInViewport();
			});
		});
	}
}
