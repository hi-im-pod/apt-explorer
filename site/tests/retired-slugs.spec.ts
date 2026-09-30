import { readFileSync } from 'node:fs';
import { test, expect, type Page } from '@playwright/test';
import type { SlugRegistry } from '../src/lib/data/types';

// The stubs come from data/slugs.json, so the expectations come from it too. Before the first
// real build has committed that file, or while no two actors have been merged, there is no stub
// to look at, and the tests that need one say so instead of passing without checking anything.
function readRegistry(): SlugRegistry {
	try {
		return JSON.parse(readFileSync(new URL('../../data/slugs.json', import.meta.url), 'utf8'));
	} catch {
		return { entries: [] };
	}
}

const registry = readRegistry();
const live = new Map(registry.entries.filter((e) => !e.retired).map((e) => [e.slug, e]));
const merged = registry.entries.filter((e) => e.retired && e.merged_into !== null && live.has(e.merged_into));
const themes = ['light', 'dark', 'apt'] as const;

async function useTheme(page: Page, t: string) {
	await page.addInitScript((th) => {
		try {
			localStorage.setItem('theme', th);
		} catch {}
	}, t);
}

test.describe('a merged slug', () => {
	test.skip(merged.length === 0, 'data/slugs.json has no merged slug yet');

	test('says the actor was merged and links to the one that took over', async ({ page }) => {
		for (const e of merged) {
			const successor = live.get(e.merged_into!)!;
			const res = await page.goto(`/apt-explorer/actors/${e.slug}/`);
			expect(res?.status(), e.slug).toBe(200);
			await expect(page.getByRole('heading', { level: 1 })).toHaveText(
				`${e.display_name} was merged into ${successor.display_name}`
			);
			const link = page.getByRole('link', { name: `Go to the profile of ${successor.display_name}` });
			await expect(link).toBeVisible();
			await expect(link).toHaveAttribute('href', `/apt-explorer/actors/${successor.slug}/`);
			await expect(page).toHaveTitle(`${e.display_name} was merged · Actors · APT Explorer`);
			await expect(page.locator('meta[name="robots"]')).toHaveAttribute('content', 'noindex');
		}
	});

	test('follows the link to a profile that still exists', async ({ page }) => {
		const e = merged[0];
		const successor = live.get(e.merged_into!)!;
		await page.goto(`/apt-explorer/actors/${e.slug}/`);
		await page.getByRole('link', { name: `Go to the profile of ${successor.display_name}` }).click();
		await expect(page).toHaveURL(`/apt-explorer/actors/${successor.slug}/`);
		await expect(page.getByRole('heading', { level: 1 })).toHaveText(successor.display_name);
	});

	test('shows no profile sections, because nothing on it is about an actor', async ({ page }) => {
		await page.goto(`/apt-explorer/actors/${merged[0].slug}/`);
		await expect(page.getByRole('heading', { level: 2 })).toHaveCount(0);
		await expect(page.getByText('Merge evidence')).toHaveCount(0);
	});

	for (const [width, height] of [
		[1280, 800],
		[375, 800]
	] as const) {
		for (const t of themes) {
			test(`at ${width}px in ${t}, the stub is painted, readable and inside the screen`, async ({ page }, info) => {
				await useTheme(page, t);
				await page.setViewportSize({ width, height });
				await page.goto(`/apt-explorer/actors/${merged[0].slug}/`);
				const h1 = page.getByRole('heading', { level: 1 });
				const link = page.getByRole('link', { name: /^Go to the profile of / });
				await expect(h1).toBeVisible();
				for (const el of [h1, link]) {
					const box = await el.boundingBox();
					expect(box, 'the element is painted').not.toBeNull();
					expect(box!.width).toBeGreaterThan(0);
					expect(box!.height).toBeGreaterThan(0);
					expect(box!.x).toBeGreaterThanOrEqual(0);
					expect(box!.x + box!.width).toBeLessThanOrEqual(width);
				}
				// No sideways scroll, and the heading is set in a real size, not the browser default.
				expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
				expect(await h1.evaluate((el) => parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThan(20);
				// The link is not the same colour as the page behind it, so it can be seen.
				const colours = await link.evaluate((el) => ({
					link: getComputedStyle(el).color,
					page: getComputedStyle(document.body).backgroundColor
				}));
				expect(colours.link).not.toBe(colours.page);
				if (t === 'light') await page.screenshot({ path: info.outputPath(`stub-${width}.png`), fullPage: true });
			});
		}
	}
});

test('a live actor page is not a stub', async ({ page }) => {
	const [slug, entry] = [...live][0] ?? [];
	test.skip(!slug, 'data/slugs.json has no live entry yet');
	await page.goto(`/apt-explorer/actors/${slug}/`);
	await expect(page.getByRole('heading', { level: 1 })).toHaveText(entry!.display_name);
	await expect(page.getByRole('heading', { level: 2, name: 'Aliases' })).toBeVisible();
	await expect(page.getByRole('link', { name: /^Go to the profile of / })).toHaveCount(0);
	await expect(page.locator('meta[name="robots"]')).toHaveCount(0);
});

test('a retired slug that was never merged is still the site\'s own not-found page', async ({ page }) => {
	const vanished = registry.entries.find((e) => e.retired && e.merged_into === null);
	test.skip(!vanished, 'data/slugs.json has no vanished slug');
	const res = await page.goto(`/apt-explorer/actors/${vanished!.slug}/`);
	expect(res?.status()).toBe(404);
});
