import { readFileSync } from 'node:fs';
import { test, expect, type Page } from '@playwright/test';
import type { Sources } from '../src/lib/data/types';

// The same sources.json the site is built from. The page must show what the
// data says, so the expectations come from the data, not from a copy.
const sources: Sources = JSON.parse(
	readFileSync(new URL('../../data/sources.json', import.meta.url), 'utf8')
);
const byName = (name: string) => {
	const s = sources.find((x) => x.name === name);
	if (!s) throw new Error(`${name} is not in sources.json`);
	return s;
};
const themes = ['light', 'dark', 'apt'] as const;
const ABOUT = '/apt-explorer/about/';

async function useTheme(page: Page, t: string) {
	await page.addInitScript((th) => {
		try {
			localStorage.setItem('theme', th);
		} catch {}
	}, t);
}

test('every source shows its licence, licence link, publish value and attribution', async ({ page }) => {
	await page.goto(ABOUT);
	expect(sources.length).toBeGreaterThan(0);
	for (const s of sources) {
		const card = page.locator(`#source-${s.name}`);
		await expect(card, s.name).toBeVisible();
		await expect(card.getByRole('link', { name: s.licence, exact: true })).toHaveAttribute(
			'href',
			s.licence_url
		);
		await expect(card).toContainText(s.attribution);
		await expect(card).toContainText(s.publish);
	}
});

test('a stale source says so on the About page', async ({ page }) => {
	await page.goto(ABOUT);
	for (const s of sources) {
		const card = page.locator(`#source-${s.name}`);
		if (s.stale) await expect(card).toContainText(/stale/i);
		else await expect(card).not.toContainText(/stale/i);
	}
});

test('the data licence notice gives CC BY-NC-SA 4.0 and MITRE\'s full notice', async ({ page }) => {
	await page.goto(ABOUT);
	const notice = page.locator('#data-licence');
	await expect(notice.getByRole('heading', { level: 2 })).toHaveText('Data Licence');
	await expect(
		notice.locator('a[href="https://creativecommons.org/licenses/by-nc-sa/4.0/"]').first()
	).toBeVisible();
	await expect(notice).toContainText('CC BY-NC-SA 4.0');
	await expect(notice).toContainText(/no additional terms/i);
	// The attack attribution is MITRE's copyright designation, licence
	// paragraph and trademark line, which must travel with the data.
	await expect(notice).toContainText(byName('attack').attribution);
	// Prerendered links may be relative, so compare where the link resolves.
	const file = notice.getByRole('link', { name: /NOTICE\.md/ });
	expect(new URL(await file.evaluate((a) => (a as HTMLAnchorElement).href)).pathname).toBe(
		'/apt-explorer/data/NOTICE.md'
	);
});

test('the paper is credited with its CC BY 4.0 attribution and links', async ({ page }) => {
	await page.goto(ABOUT);
	const paper = page.locator('#paper');
	await expect(paper).toContainText('Yuldoshkhujaev');
	await expect(paper).toContainText("CCS '25");
	await expect(paper).toContainText(byName('paper').attribution);
	for (const href of [
		'https://arxiv.org/abs/2509.07457',
		'https://zenodo.org/records/16869733',
		byName('paper').licence_url
	]) {
		await expect(paper.locator(`a[href="${href}"]`).first(), href).toBeVisible();
	}
});

test('every publish value is explained, evidence-only included', async ({ page }) => {
	await page.goto(ABOUT);
	const values = page.locator('#publish-values');
	for (const p of ['full', 'derived-only', 'link-only', 'evidence-only']) {
		await expect(values.locator('dt', { hasText: p }).first(), p).toBeVisible();
	}
	await expect(values).toContainText(/nothing from the source appears in the published data/i);
});

test('MITRE ATT&CK is named as MITRE asks', async ({ page }) => {
	await page.goto(ABOUT);
	// Headings read "MITRE ATT&CK" with no sign.
	const headings = await page.getByRole('heading').allInnerTexts();
	expect(headings.some((h) => h.includes('MITRE ATT&CK'))).toBe(true);
	for (const h of headings) expect(h).not.toContain('®');
	// The first mention in the page's text carries the sign.
	const text = await page.locator('main').innerText();
	const first = text.indexOf('ATT&CK');
	expect(text.slice(first, first + 7)).toBe('ATT&CK®');
});

for (const t of themes) {
	test(`at 375px in ${t}, every source card and notice fits the screen`, async ({ page }) => {
		await page.setViewportSize({ width: 375, height: 800 });
		await useTheme(page, t);
		await page.goto(ABOUT);
		// The document scroll width alone misses content clipped inside a
		// box with overflow hidden or auto, so check each box as well.
		const boxes = page.locator('[id^="source-"], #data-licence, #paper, #publish-values');
		const n = await boxes.count();
		expect(n).toBe(sources.length + 3);
		for (let i = 0; i < n; i++) {
			const box = await boxes.nth(i).boundingBox();
			expect(box, `box ${i}`).not.toBeNull();
			expect(box!.x).toBeGreaterThanOrEqual(0);
			expect(box!.x + box!.width).toBeLessThanOrEqual(375);
			const clipped = await boxes
				.nth(i)
				.evaluate((el) =>
					[el, ...el.querySelectorAll('*')].some((e) => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'visible')
				);
			expect(clipped, `box ${i} clips content`).toBe(false);
		}
		expect(
			await page.evaluate(
				() => document.documentElement.scrollWidth <= document.documentElement.clientWidth
			)
		).toBe(true);
	});
}

test('with scripts blocked, the prerendered About page still reads', async ({ page }) => {
	// A blocked script is the failure that happens (an extension, a policy),
	// and <noscript> does not fire for it, so block the files themselves.
	await page.route('**/*.js', (r) => r.abort());
	await page.goto(ABOUT);
	await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
	await expect(page.locator('#source-attack')).toContainText(byName('attack').attribution);
	await expect(page.locator('#paper').locator('a[href="https://arxiv.org/abs/2509.07457"]')).toBeVisible();
	expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).not.toBe(
		'rgba(0, 0, 0, 0)'
	);
});
