import { readFileSync } from 'node:fs';
import { test, expect, type Page } from '@playwright/test';
import type { ActorsIndex, Resolution, Sources } from '../src/lib/data/types';
import { PUBLISH_POLICIES } from '../src/lib/data/labels';

// The page must show what this build's data says, so the expectations are
// read from the same files the site is built from.
const DATA = new URL('../../data/', import.meta.url);
const readJson = <T>(path: string): T => JSON.parse(readFileSync(new URL(path, DATA), 'utf8')) as T;
const resolution = readJson<Resolution>('resolution.json');
const sources = readJson<Sources>('sources.json');
const index = readJson<ActorsIndex>('actors/index.json');

const PAGE = '/apt-explorer/methodology/';
const themes = ['light', 'dark', 'apt'] as const;
const count = (n: number) => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');

async function useTheme(page: Page, t: string) {
	await page.addInitScript((th) => {
		try {
			localStorage.setItem('theme', th);
		} catch {}
	}, t);
}

test('the page shows the registry counts', async ({ page }) => {
	await page.goto(PAGE);
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Methodology');
	const stats = page.locator('#registry');
	for (const [label, value] of [
		[/source records/i, resolution.stats.source_record_count],
		[/^actors$/i, resolution.stats.actor_count],
		[/^merges$/i, resolution.stats.merge_count],
		[/evidence links/i, resolution.stats.evidence_edge_count],
		[/ambiguous aliases/i, resolution.stats.ambiguity_count],
		[/typed as software/i, resolution.stats.non_actor_name_count]
	] as const) {
		const term = stats.locator('dt', { hasText: label });
		await expect(term, String(label)).toHaveCount(1);
		await expect(term.locator('xpath=following-sibling::dd[1]')).toHaveText(count(value));
	}
});

test("the page gives the match rate against the paper's names", async ({ page }) => {
	const m = resolution.paper_match;
	await page.goto(PAGE);
	const section = page.locator('#paper-match');
	await expect(section).toContainText(`${(m.match_rate! * 100).toFixed(1)}%`);
	await expect(section).toContainText(`${count(m.names_total)} actor names`);
	await expect(section).toContainText(count(m.resolved));
	await expect(section).toContainText(count(m.typed_non_actor));
	await expect(section).toContainText(count(m.names_total - m.resolved - m.typed_non_actor));
});

test('the ambiguities are a table, each candidate linking to its profile', async ({ page }) => {
	await page.goto(PAGE);
	const table = page.locator('#ambiguities').getByRole('table');
	await expect(table).toBeVisible();
	const rows = table.locator('tbody tr');
	await expect(rows).toHaveCount(resolution.ambiguities.length);
	for (const [i, a] of resolution.ambiguities.entries()) {
		await expect(rows.nth(i)).toContainText(a.alias);
		for (const id of a.candidates) {
			const name = index.find((x) => x.id === id)!.name;
			const link = rows.nth(i).getByRole('link', { name, exact: true });
			const href = await link.evaluate((el) => new URL((el as HTMLAnchorElement).href).pathname);
			expect(href).toBe(`/apt-explorer/actors/${id}/`);
		}
	}
});

test('the unresolved names are listed with how each was typed', async ({ page }) => {
	await page.goto(PAGE);
	const rows = page.locator('#unresolved').getByRole('table').locator('tbody tr');
	await expect(rows).toHaveCount(resolution.unresolved_names.length);
	for (const [i, n] of resolution.unresolved_names.entries()) {
		await expect(rows.nth(i)).toContainText(n.name);
		await expect(rows.nth(i)).toContainText(n.typed_as ?? 'not typed');
	}
});

test('the date-basis rules are stated in order, with what happens to undated reports', async ({ page }) => {
	await page.goto(PAGE);
	const dates = page.locator('#report-dates');
	const steps = dates.getByRole('listitem');
	await expect(steps).toHaveCount(4);
	await expect(steps.nth(0)).toContainText(/malpedia library/i);
	await expect(steps.nth(1)).toContainText(/date at the start of the report's title/i);
	await expect(steps.nth(1)).toContainText(/not later than the day ORKL\s+added the report/i);
	await expect(steps.nth(2)).toContainText(/file creation/i);
	await expect(steps.nth(3)).toContainText(/ORKL added/i);
	await expect(dates).toContainText(/undated/i);
	await expect(dates).toContainText(/never in a timeline or a trend/i);
	await expect(dates).toContainText('0001-01-01');
});

test('the evidence-only rule is stated, with the sources that use it in this build', async ({ page }) => {
	await page.goto(PAGE);
	const rules = page.locator('#publishing');
	await expect(rules).toContainText(PUBLISH_POLICIES['evidence-only']);
	const evidenceOnly = sources.filter((s) => s.publish === 'evidence-only');
	if (evidenceOnly.length === 0) await expect(rules).toContainText(/no source is evidence-only in this build/i);
	// ORKL's actor tags stay out of view while ORKL is link-only.
	if (sources.find((s) => s.name === 'orkl')?.publish === 'link-only') {
		await expect(rules).toContainText(/never shows those tags/i);
		await expect(rules).toContainText(/were added by this project/i);
	}
	const about = rules.getByRole('link', { name: /about/i }).first();
	expect(await about.evaluate((el) => new URL((el as HTMLAnchorElement).href).pathname)).toBe('/apt-explorer/about/');
});

test('MITRE ATT&CK is named as MITRE asks', async ({ page }) => {
	await page.goto(PAGE);
	const headings = await page.getByRole('heading').allInnerTexts();
	for (const h of headings) expect(h).not.toContain('®');
	const text = await page.locator('main').innerText();
	const first = text.indexOf('ATT&CK');
	expect(first).toBeGreaterThan(-1);
	expect(text.slice(first, first + 7)).toBe('ATT&CK®');
});

test('a build without the paper data, or with an unpublished candidate, still renders', async ({ page }) => {
	// Answer a client-side visit with a resolution.json the sample does not
	// cover: no paper match, an ambiguity naming an ID that has no profile,
	// and no unresolved names.
	const edited: Resolution = {
		...resolution,
		paper_match: { ...resolution.paper_match, resolved: 0, typed_non_actor: 0, match_rate: null },
		ambiguities: [{ alias: 'ghostkey', candidates: [index[0].id, 'G9999'] }],
		unresolved_names: []
	};
	await page.route('**/apt-explorer/data/resolution.json', (r) =>
		r.fulfill({ contentType: 'application/json', body: JSON.stringify(edited) })
	);
	await page.goto('/apt-explorer/');
	await page.getByRole('contentinfo').getByRole('link', { name: 'Methodology' }).click();
	await expect(page).toHaveURL(/\/methodology\/$/);
	await expect(page.locator('#paper-match')).toContainText(/not available for this build/i);
	const row = page.locator('#ambiguities tbody tr');
	await expect(row).toHaveCount(1);
	await expect(row.getByRole('link')).toHaveCount(1);
	await expect(row).toContainText('G9999');
	await expect(page.locator('#unresolved')).toContainText(/every report actor name in this build resolved/i);
	await expect(page.locator('#unresolved table')).toHaveCount(0);
});

for (const t of themes) {
	test(`at 375px in ${t}, the methodology page fits the screen`, async ({ page }) => {
		await page.setViewportSize({ width: 375, height: 800 });
		await useTheme(page, t);
		await page.goto(PAGE);
		await expect(page.locator('html')).toHaveAttribute('data-theme', t);
		const report = await page.evaluate(() => {
			const clipped = [...document.querySelectorAll('main, main *')]
				.filter((e) => !e.closest('.visually-hidden'))
				.filter((e) => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'visible')
				.map((e) => `${e.tagName}.${e.className}`);
			return { scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth, clipped };
		});
		expect(report.clipped).toEqual([]);
		expect(report.scroll).toBeLessThanOrEqual(report.client);
	});
}

test('with scripts blocked, the prerendered methodology page still reads', async ({ page }) => {
	await page.route('**/*.js', (r) => r.abort());
	await page.goto(PAGE);
	await expect(page.locator('#paper-match')).toContainText(`${(resolution.paper_match.match_rate! * 100).toFixed(1)}%`);
	await expect(page.locator('#ambiguities').getByRole('table')).toBeVisible();
});

test('the methodology page loads without console errors', async ({ page }) => {
	const errors: string[] = [];
	page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
	page.on('pageerror', (e) => errors.push(e.message));
	await page.goto(PAGE);
	await page.waitForLoadState('networkidle');
	expect(errors).toEqual([]);
});
