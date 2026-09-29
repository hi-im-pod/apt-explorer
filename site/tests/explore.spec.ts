import { readFileSync } from 'node:fs';
import { test, expect, type Locator, type Page } from '@playwright/test';
import type { ActorsIndex, Build, Campaigns, Report, Vulns } from '../src/lib/data/types';

// Expectations come from the same data/ the site is built from, so a change
// to the sample changes what these tests expect rather than breaking them.
const read = <T>(path: string): T =>
	JSON.parse(readFileSync(new URL(`../../data/${path}`, import.meta.url), 'utf8')) as T;
const build = read<Build>('build.json');
const reports: Report[] = [
	...build.report_years.flatMap((y) => read<Report[]>(`reports/${y}.json`)),
	...read<Report[]>('reports/undated.json')
];
const campaigns = read<Campaigns>('campaigns.json');
const vulns = read<Vulns>('vulns.json');
const actors = read<ActorsIndex>('actors/index.json');
const nameOf = (id: string) => actors.find((a) => a.id === id)?.name ?? id;
const kevCves = new Set(vulns.filter((v) => v.kev_date_added).map((v) => v.cve));
const reportById = (id: string) => {
	const r = reports.find((x) => x.id === id);
	if (!r) throw new Error(`${id} is not in the sample reports`);
	return r;
};

const EXPLORE = '/apt-explorer/explore/';
const themes = ['light', 'dark', 'apt'] as const;
const dated = reports.filter((r) => r.published != null);
const undated = reports.filter((r) => r.published == null);

// Sample rows with a known shape, named once so each test says what it needs.
const ORKL_DEAD = '83086f8202f48adfac618fb3cab581faf271d0f0'; // ORKL, url_ok false, has an archive link
const ORKL_LIVE = '28d4a0de3aaa5bc79df8b62aa641beefae28b106'; // ORKL, url_ok true, has an archive link
const ORKL_NO_URL = 'b7e85ac766fe089afaf42198525b8acec729c467'; // ORKL, undated, no original URL
const PAPER_DEAD = 'paper:2023_mass_exploitation_of_a_managed_file_transfer_server.pdf'; // no archive
const PAPER_LIVE = 'paper:2023_dns_tunnelling_backdoor_in_middle_east_government_networks.pdf';

async function useTheme(page: Page, t: string) {
	await page.addInitScript((th) => {
		try {
			localStorage.setItem('theme', th);
		} catch {}
	}, t);
}

/** Open a URL and wait until the rows have loaded in the browser. */
async function open(page: Page, query = '') {
	await page.goto(`${EXPLORE}${query}`);
	await expect(page.getByRole('status')).toContainText(/showing/i);
}

const table = (page: Page) => page.getByRole('table', { name: /reports and campaigns/i });
/** Body rows only: the header row holds column headers, not cells. */
const bodyRows = (page: Page) => table(page).getByRole('row').filter({ has: page.getByRole('cell') });
const rowFor = (page: Page, title: string) => bodyRows(page).filter({ hasText: title });
const panel = (page: Page) => page.getByRole('dialog');

async function shownCount(page: Page): Promise<number> {
	const text = await page.getByRole('status').innerText();
	const m = /showing ([\d,]+)/i.exec(text);
	if (!m) throw new Error(`no count in "${text}"`);
	return Number(m[1].replace(/,/g, ''));
}

async function noHorizontalScroll(page: Page) {
	expect(
		await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)
	).toBe(true);
}

async function hrefPath(link: Locator) {
	return new URL(await link.evaluate((a) => (a as HTMLAnchorElement).href)).pathname;
}

// ---------------------------------------------------------------------------
// The plan's cases.

test('an actor and start date in the URL show only that actor from that date', async ({ page }) => {
	await open(page, '?actor=G0007&from=2024-01-01');
	const expected =
		dated.filter((r) => r.actors.includes('G0007') && r.published! >= '2024-01-01').length +
		campaigns.filter((c) => c.actors.includes('G0007')).length;
	expect(expected).toBeGreaterThan(3);
	expect(await shownCount(page)).toBe(expected);
	const rows = bodyRows(page);
	await expect(rows).toHaveCount(expected);
	for (let i = 0; i < expected; i++) {
		await expect(rows.nth(i).getByRole('listitem').filter({ hasText: /^APT28$/ })).toBeVisible();
	}
	// The controls show the state the URL asked for.
	await expect(page.getByLabel('Actor', { exact: true })).toHaveValue('G0007');
	await expect(page.getByLabel('From', { exact: true })).toHaveValue('2024-01-01');
});

test('clicking a row sets ?report= and opens the panel with the original and archive links', async ({ page }) => {
	await open(page);
	const r = reportById(ORKL_DEAD);
	await rowFor(page, r.title).getByRole('link').click();
	await expect(page).toHaveURL(new RegExp(`[?&]report=${ORKL_DEAD}`));
	const dialog = panel(page);
	await expect(dialog).toBeVisible();
	await expect(dialog.getByRole('heading', { level: 2 })).toHaveText(r.title);
	await expect(dialog.getByRole('link', { name: /original/i })).toHaveAttribute('href', r.url!);
	await expect(dialog.getByRole('link', { name: /archive/i })).toHaveAttribute('href', r.archive_url!);
});

test('reloading a ?report= URL reopens the same panel', async ({ page }) => {
	await open(page, `?report=${ORKL_DEAD}`);
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText(reportById(ORKL_DEAD).title);
	await page.reload();
	await expect(panel(page).getByRole('heading', { level: 2 })).toHaveText(reportById(ORKL_DEAD).title);
});

for (const t of themes) {
	test(`at 375px in ${t}, rows become cards with no horizontal scroll`, async ({ page }) => {
		await page.setViewportSize({ width: 375, height: 800 });
		await useTheme(page, t);
		await open(page);
		const rows = bodyRows(page);
		const n = Math.min(await rows.count(), 6);
		expect(n).toBeGreaterThan(0);
		for (let i = 0; i < n; i++) {
			const row = rows.nth(i);
			const box = (await row.boundingBox())!;
			expect(box.x).toBeGreaterThanOrEqual(0);
			expect(box.x + box.width).toBeLessThanOrEqual(375);
			// A card stacks the title under the date, where a table row puts
			// them side by side.
			const date = (await row.getByRole('cell').nth(0).boundingBox())!;
			const title = (await row.getByRole('cell').nth(1).boundingBox())!;
			expect(title.y).toBeGreaterThanOrEqual(date.y + date.height - 1);
		}
		await expect(table(page).getByRole('columnheader').first()).not.toBeInViewport();
		await noHorizontalScroll(page);

		// The open panel fits the screen too.
		await rows.first().getByRole('link').click();
		const dbox = (await panel(page).boundingBox())!;
		expect(dbox.x).toBeGreaterThanOrEqual(0);
		expect(dbox.x + dbox.width).toBeLessThanOrEqual(375);
		await noHorizontalScroll(page);
	});
}

test('at 375px the other filters fold away, so the rows start on the first screen', async ({ page }) => {
	await page.setViewportSize({ width: 375, height: 800 });
	await open(page, '?actor=G0007');
	await expect(bodyRows(page).first()).toBeInViewport();
	await expect(page.getByLabel('Actor', { exact: true })).toBeHidden();
	const toggle = page.getByRole('button', { name: /more filters/i });
	await expect(toggle).toContainText('1 on');
	await toggle.click();
	await expect(page.getByRole('button', { name: /fewer filters/i })).toHaveAttribute('aria-expanded', 'true');
	await expect(page.getByLabel('Actor', { exact: true })).toHaveValue('G0007');
});

// Rows have a fixed height so the window can map a scroll position to a row.
// A theme with a wider font must not push a cell past the row's edge, where
// it would be clipped without anyone noticing.
for (const w of [1280, 375]) {
	for (const t of themes) {
		test(`every row's cells fit inside the row at ${w}px in ${t}`, async ({ page }) => {
			await page.setViewportSize({ width: w, height: 900 });
			await useTheme(page, t);
			await open(page, '?undated=1');
			await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
			await page.evaluate(() => window.scrollTo(0, 0));
			const overflow = await table(page).evaluate((el) => {
				const bad: string[] = [];
				for (const row of el.querySelectorAll<HTMLElement>('[role="rowgroup"]:last-child [role="row"]')) {
					const bottom = row.getBoundingClientRect().bottom;
					for (const cell of row.querySelectorAll<HTMLElement>('[role="cell"]')) {
						if (cell.getBoundingClientRect().bottom > bottom + 0.5) bad.push(cell.innerText.slice(0, 40));
					}
				}
				return bad;
			});
			expect(overflow).toEqual([]);
		});
	}
}

test('at 1280px the row cells sit side by side', async ({ page }) => {
	await page.setViewportSize({ width: 1280, height: 900 });
	await open(page);
	const row = bodyRows(page).first();
	const date = (await row.getByRole('cell').nth(0).boundingBox())!;
	const title = (await row.getByRole('cell').nth(1).boundingBox())!;
	expect(title.x).toBeGreaterThan(date.x + date.width - 1);
	await expect(table(page).getByRole('columnheader', { name: 'Date' })).toBeVisible();
});

test('undated reports appear only when the Undated switch is on', async ({ page }) => {
	await open(page);
	const before = await shownCount(page);
	expect(before).toBe(dated.length + campaigns.length);
	await page.getByLabel(/include undated reports/i).check();
	await expect(page).toHaveURL(/[?&]undated=1/);
	await expect.poll(() => shownCount(page)).toBe(before + undated.length);
	// Undated rows sort last, so they are rendered once scrolled to.
	await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
	await expect(rowFor(page, undated[0].title)).toBeVisible();
	await expect(rowFor(page, undated[0].title).getByRole('cell').first()).toHaveText(/undated/i);

	await page.getByLabel(/include undated reports/i).uncheck();
	await expect(page).not.toHaveURL(/undated=/);
	await expect.poll(() => shownCount(page)).toBe(before);
});

// ---------------------------------------------------------------------------
// The detail panel.

test('a live original link comes first, and a non-ORKL report shows its full details', async ({ page }) => {
	const r = reportById(PAPER_LIVE);
	await open(page, `?report=${encodeURIComponent(PAPER_LIVE)}`);
	const dialog = panel(page);
	const links = dialog.getByRole('list', { name: /links/i }).getByRole('link');
	await expect(links.first()).toHaveAttribute('href', r.url!);
	await expect(dialog).not.toContainText(/unreachable/i);
	await expect(dialog).toContainText(r.organisation!);
	for (const id of r.actors) {
		const link = dialog.getByRole('link', { name: nameOf(id), exact: true });
		expect(await hrefPath(link)).toBe(`/apt-explorer/actors/${id}/`);
	}
	for (const name of r.actor_names_unresolved) await expect(dialog).toContainText(name);
	for (const tid of r.techniques) await expect(dialog).toContainText(tid);
	await expect(dialog).toContainText(/CCS '25/);
});

test('an unreachable original puts the archive link first and says why', async ({ page }) => {
	await open(page, `?report=${ORKL_DEAD}`);
	const dialog = panel(page);
	const links = dialog.getByRole('list', { name: /links/i }).getByRole('link');
	await expect(links.first()).toHaveAttribute('href', reportById(ORKL_DEAD).archive_url!);
	await expect(links.nth(1)).toHaveAttribute('href', reportById(ORKL_DEAD).url!);
	await expect(dialog).toContainText(/original .*unreachable/i);
});

test('an unreachable original with no archive copy is still linked, with the warning', async ({ page }) => {
	const r = reportById(PAPER_DEAD);
	await open(page, `?report=${encodeURIComponent(PAPER_DEAD)}`);
	const dialog = panel(page);
	const links = dialog.getByRole('list', { name: /links/i }).getByRole('link');
	await expect(links).toHaveCount(1);
	await expect(links.first()).toHaveAttribute('href', r.url!);
	await expect(dialog).toContainText(/original .*unreachable/i);
	// Its CVE is in KEV, and the panel says so.
	const cve = r.cves[0];
	expect(kevCves.has(cve)).toBe(true);
	await expect(dialog.getByRole('listitem').filter({ hasText: cve })).toContainText(/KEV/);
});

test('a report with no original URL offers the archive copy', async ({ page }) => {
	await open(page, `?report=${ORKL_NO_URL}`);
	const dialog = panel(page);
	const links = dialog.getByRole('list', { name: /links/i }).getByRole('link');
	await expect(links).toHaveCount(1);
	await expect(links.first()).toHaveAttribute('href', reportById(ORKL_NO_URL).archive_url!);
	await expect(dialog).toContainText(/no original link/i);
});

test('an ORKL report shows only its title, date and links', async ({ page }) => {
	const r = reportById(ORKL_LIVE);
	await open(page, `?report=${ORKL_LIVE}`);
	const dialog = panel(page);
	await expect(dialog.getByRole('heading', { level: 2 })).toHaveText(r.title);
	await expect(dialog.locator('time')).toHaveAttribute('datetime', r.published!);
	// The archive copy is only a fallback for a live ORKL original.
	const links = dialog.getByRole('list', { name: /links/i }).getByRole('link');
	await expect(links).toHaveCount(1);
	await expect(links.first()).toHaveAttribute('href', r.url!);
	for (const id of r.actors) await expect(dialog).not.toContainText(nameOf(id));
	for (const cve of r.cves) await expect(dialog).not.toContainText(cve);
	for (const tid of r.techniques) await expect(dialog).not.toContainText(tid);
	await expect(dialog).toContainText(/link-only/i);
});

test("ORKL's actor tags never appear, in the table or the panel", async ({ page }) => {
	// Route a shard with an ORKL row that carries names the registry left
	// unresolved. The contract keeps these empty for link-only rows, and the
	// site must not show them even if a build gets that wrong.
	const TAG = 'Leaky Tag Panda';
	await page.route('**/data/reports/2026.json', async (route) => {
		const shard = (await (await route.fetch()).json()) as Report[];
		shard[0] = { ...shard[0], sources: ['orkl'], actor_names_unresolved: [TAG] };
		await route.fulfill({ json: shard });
	});
	await open(page, `?q=${encodeURIComponent(TAG)}`);
	expect(await shownCount(page)).toBe(0);
	const id = read<Report[]>('reports/2026.json')[0].id;
	await page.goto(`${EXPLORE}?report=${encodeURIComponent(id)}`);
	await expect(panel(page)).toBeVisible();
	await expect(page.locator('body')).not.toContainText(TAG);
});

test('a campaign opens through ?campaign= with its span, actors and ATT&CK link', async ({ page }) => {
	const c = campaigns.find((x) => x.id === 'C0022')!;
	await open(page);
	await rowFor(page, c.name).getByRole('link').click();
	await expect(page).toHaveURL(/[?&]campaign=C0022/);
	await expect(page).not.toHaveURL(/report=/);
	const dialog = panel(page);
	await expect(dialog.getByRole('heading', { level: 2 })).toHaveText(c.name);
	await expect(dialog.locator(`time[datetime="${c.first_seen}"]`)).toBeVisible();
	await expect(dialog.locator(`time[datetime="${c.last_seen}"]`)).toBeVisible();
	expect(await hrefPath(dialog.getByRole('link', { name: nameOf(c.actors[0]), exact: true }))).toBe(
		`/apt-explorer/actors/${c.actors[0]}/`
	);
	await expect(dialog.getByRole('link', { name: /att&ck/i })).toHaveAttribute(
		'href',
		'https://attack.mitre.org/campaigns/C0022/'
	);
});

test('an unknown ?report= says it is not in the data', async ({ page }) => {
	await open(page, '?report=zzz-not-a-report');
	await expect(panel(page)).toContainText(/not in the current data/i);
});

test('the panel takes focus, closes on Escape, clears ?report= and returns focus to the row', async ({ page }) => {
	await open(page);
	const r = reportById(ORKL_DEAD);
	const link = rowFor(page, r.title).getByRole('link');
	await link.click();
	const dialog = panel(page);
	await expect(dialog).toBeVisible();
	expect(await dialog.evaluate((d) => d.contains(document.activeElement))).toBe(true);
	await page.keyboard.press('Escape');
	await expect(dialog).toBeHidden();
	await expect(page).not.toHaveURL(/report=/);
	await expect(link).toBeFocused();
});

test('the close button closes the panel and keeps the filters', async ({ page }) => {
	await open(page, `?actor=G0007&report=${ORKL_DEAD}`);
	await panel(page).getByRole('button', { name: /close/i }).click();
	await expect(panel(page)).toBeHidden();
	await expect(page).toHaveURL(/\?actor=G0007$/);
});

// ---------------------------------------------------------------------------
// Filters and the URL.

test('the KEV switch keeps rows that name a KEV CVE and is written to the URL', async ({ page }) => {
	await open(page);
	await page.getByLabel(/only cves in cisa kev/i).check();
	await expect(page).toHaveURL(/[?&]kev=1/);
	const expected = dated.filter((r) => r.cves.some((c) => kevCves.has(c))).length;
	expect(expected).toBeGreaterThan(0);
	await expect.poll(() => shownCount(page)).toBe(expected);
});

test('text search matches actor aliases and is written to the URL', async ({ page }) => {
	await open(page);
	await page.getByLabel('Search', { exact: true }).fill('fancy bear');
	await expect(page).toHaveURL(/[?&]q=fancy(\+|%20)bear/);
	const expected = dated.filter((r) => r.actors.includes('G0007')).length;
	await expect.poll(() => shownCount(page)).toBe(expected);
	const rows = bodyRows(page);
	for (let i = 0; i < Math.min(expected, 5); i++) await expect(rows.nth(i)).toContainText('APT28');
});

test('source, publisher, CVE and technique filters narrow the rows', async ({ page }) => {
	await open(page);
	await page.getByLabel('Source', { exact: true }).selectOption('dfir');
	await expect(page).toHaveURL(/[?&]source=dfir/);
	await expect
		.poll(() => shownCount(page))
		.toBe(
			dated.filter((r) => r.sources.includes('dfir')).length +
				campaigns.filter((c) => c.source === 'dfir').length
		);
	await page.getByRole('button', { name: /clear filters/i }).click();
	await expect(page).not.toHaveURL(/source=/);

	await page.getByLabel('CVE', { exact: true }).fill('CVE-2021-44228');
	await expect(page).toHaveURL(/[?&]cve=CVE-2021-44228/);
	await expect.poll(() => shownCount(page)).toBe(dated.filter((r) => r.cves.includes('CVE-2021-44228')).length);
	await page.getByRole('button', { name: /clear filters/i }).click();

	await page.goto(`${EXPLORE}?tech=T1566`);
	await expect(page.getByLabel('Technique', { exact: true })).toHaveValue('T1566');
	const withTech = (ts: string[]) => ts.some((t) => t.startsWith('T1566'));
	await expect
		.poll(() => shownCount(page))
		.toBe(dated.filter((r) => withTech(r.techniques)).length + campaigns.filter((c) => withTech(c.techniques)).length);
});

test('the publisher list leaves out ORKL publishers', async ({ page }) => {
	await open(page);
	const options = await page.getByLabel('Publisher', { exact: true }).locator('option').allInnerTexts();
	const nonOrkl = new Set(
		reports.filter((r) => !r.sources.includes('orkl') && r.organisation).map((r) => r.organisation!)
	);
	expect(options.slice(1).sort()).toEqual([...nonOrkl].sort());
});

test('a filter in the URL and a clear leave no history entries behind', async ({ page }) => {
	await open(page);
	const length = await page.evaluate(() => history.length);
	await page.getByLabel(/only cves in cisa kev/i).check();
	await expect(page).toHaveURL(/kev=1/);
	await page.getByRole('button', { name: /clear filters/i }).click();
	await expect(page).not.toHaveURL(/kev=1/);
	expect(await page.evaluate(() => history.length)).toBe(length);
});

// ---------------------------------------------------------------------------
// Volume, failure modes and hygiene.

test('thousands of rows render only a window of them, and scrolling reaches the last', async ({ page }) => {
	const N = 5000;
	await page.route('**/data/reports/2025.json', (route) =>
		route.fulfill({
			json: Array.from({ length: N }, (_, i) => ({
				id: `synthetic-${i}`,
				title: `Synthetic report ${i}`,
				published: `2025-${String((i % 12) + 1).padStart(2, '0')}-15`,
				date_basis: 'publisher',
				organisation: 'Fieldnote DFIR',
				url: `https://example.org/synthetic/${i}`,
				url_ok: true,
				archive_url: null,
				actors: ['G0032'],
				actor_names_unresolved: [],
				cves: [],
				techniques: [],
				sources: ['dfir']
			}))
		})
	);
	await open(page);
	expect(await shownCount(page)).toBeGreaterThan(N);
	expect(await bodyRows(page).count()).toBeLessThan(100);
	await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
	const oldest = [...campaigns, ...dated]
		.map((x) => ('name' in x ? { t: x.name, d: x.first_seen } : { t: x.title, d: x.published }))
		.filter((x) => x.d)
		.sort((a, b) => (a.d! < b.d! ? -1 : 1))[0];
	await expect(rowFor(page, oldest.t)).toBeInViewport();
	expect(await bodyRows(page).count()).toBeLessThan(100);
});

test('when the data cannot load, the page says so', async ({ page }) => {
	await page.route('**/data/campaigns.json', (route) => route.fulfill({ status: 500, body: 'no' }));
	await page.goto(EXPLORE);
	await expect(page.getByRole('alert')).toContainText(/could not be loaded/i);
});

test('with scripts blocked, the prerendered page explains that the table needs them', async ({ page }) => {
	await page.route('**/*.js', (r) => r.abort());
	await page.goto(EXPLORE);
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Explore');
	await expect(page.getByRole('status')).toContainText(/scripts/i);
});

test('the explore page loads without console errors', async ({ page }) => {
	const errors: string[] = [];
	page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
	page.on('pageerror', (e) => errors.push(e.message));
	await open(page, `?report=${ORKL_DEAD}`);
	await page.keyboard.press('Escape');
	await page.waitForLoadState('networkidle');
	expect(errors).toEqual([]);
});
