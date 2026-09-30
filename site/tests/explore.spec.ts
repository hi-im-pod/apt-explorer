import { test, expect, type Locator, type Page } from '@playwright/test';
import type { ActorsIndex, Campaigns, Report } from '../src/lib/data/types';
import { describeLinks } from '../src/lib/links';
import { INDEX, SHARD, index, read, reports, short, withExtraRows } from './explore-data';

// Expectations come from the same data the site is built from (see
// explore-data.ts), so a change to the data changes what these tests expect
// rather than breaking them.
const campaigns = read<Campaigns>('campaigns.json');
const actors = read<ActorsIndex>('actors/index.json');
const nameOf = (id: string) => actors.find((a) => a.id === id)?.name ?? id;
const kevCves = new Set(index.kev.map((p) => index.tables.cves[p]));
const reportById = (id: string) => {
	const r = reports.find((x) => x.id === id);
	if (!r) throw new Error(`${id} is not in the sample reports`);
	return r;
};

const EXPLORE = '/apt-explorer/explore/';
const themes = ['light', 'dark', 'apt'] as const;
const dated = reports.filter((r) => r.published != null);
const undated = reports.filter((r) => r.published == null);

// Rows with a known shape, named once so each test says what it needs. They are found in
// the data rather than written down, so a rebuild with different reports does not break
// them. A title made of plain words is chosen so the row can be reached by searching for it,
// because the table only renders a window of its rows.
const titleCount = new Map<string, number>();
for (const r of reports) titleCount.set(r.title, (titleCount.get(r.title) ?? 0) + 1);
const findable = (r: Report) => titleCount.get(r.title) === 1 && /^[A-Za-z0-9 ,.:'()-]{12,80}$/.test(r.title);
const orklOnly = (r: Report) => r.sources.length === 1 && r.sources[0] === 'orkl';
const paperOnly = (r: Report) => r.sources.length === 1 && r.sources[0] === 'paper';
const firstReport = (what: string, match: (r: Report) => boolean) => {
	const r = dated.find(match);
	if (!r) throw new Error(`the data has no ${what}`);
	return r;
};
const ORKL_DEAD = firstReport(
	'ORKL report with a dead publisher link and an archive copy',
	// A dead mirror is not a dead original, so the row must have a publisher link.
	(r) =>
		orklOnly(r) &&
		findable(r) &&
		r.url_ok === false &&
		!!r.archive_url &&
		describeLinks(r).links.some((l) => l.role === 'original')
).id;
const ORKL_LIVE = firstReport(
	'ORKL report with a live original and an archive copy',
	(r) => orklOnly(r) && findable(r) && r.url_ok === true && !!r.url && !!r.archive_url
).id;
// A link-only report that the pipeline linked to an actor and found a CVE and a technique in.
const ORKL_TAGGED = firstReport(
	'ORKL report with an actor, a CVE, a technique and an archive copy',
	(r) =>
		orklOnly(r) && findable(r) && r.actors.length > 0 && r.cves.length > 0 && r.techniques.length > 0 && !!r.archive_url
).id;
const ORKL_ANY = firstReport('ORKL report with an archive copy', (r) => orklOnly(r) && !!r.url && !!r.archive_url).id;
// A paper-only report with a publisher and actors, and one with a CVE that CISA lists as exploited.
const PAPER_LIVE = firstReport(
	'paper report with a publisher and actors',
	(r) => paperOnly(r) && !!r.organisation && r.actors.length > 0 && !!r.url
).id;
const PAPER_KEV = firstReport(
	'paper report with a KEV CVE',
	(r) => paperOnly(r) && !!r.url && r.cves.some((c) => kevCves.has(c))
).id;

// The live data has no report without an original link, and none whose original is dead with
// no archive copy either, so those two states are made by editing one real row on its way to
// the page. The panel is the thing under test, and it reads only what the row says.
const NO_URL = { url: null, url_ok: null } as const;
const DEAD_NO_ARCHIVE = { url_ok: false, archive_url: null } as const;
async function editReport(page: Page, id: string, patch: Partial<Report>) {
	await page.route(SHARD, async (route) => {
		const shard = (await (await route.fetch()).json()) as Report[];
		await route.fulfill({ json: shard.map((r) => (r.id === id ? { ...r, ...patch } : r)) });
	});
}
/** The address that finds a row by its own title. */
const byTitle = (id: string) => `?q=${encodeURIComponent(reportById(id).title)}`;

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
	// The page reads a 1 MB index and builds thirty thousand rows, and several workers do that at
	// once, so the default five seconds can be too short.
	await expect(status(page)).toContainText(/showing/i, { timeout: 20_000 });
}

/** The page's own count and loading note. The open panel has a status line of its own for its links. */
const status = (page: Page) => page.locator('.notice[role="status"]');
const table = (page: Page) => page.getByRole('table', { name: /reports and campaigns/i });
/** Body rows only: the header row holds column headers, not cells. */
const bodyRows = (page: Page) => table(page).getByRole('row').filter({ has: page.getByRole('cell') });
const rowFor = (page: Page, title: string) => bodyRows(page).filter({ hasText: title });
const panel = (page: Page) => page.getByRole('dialog');

async function shownCount(page: Page): Promise<number> {
	const text = await status(page).innerText();
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
	const r = reportById(ORKL_DEAD);
	await open(page, byTitle(ORKL_DEAD));
	await rowFor(page, r.title).getByRole('link').first().click();
	// The address holds the short form of the id, the same one the index stores.
	await expect(page).toHaveURL(new RegExp(`[?&]report=${short(ORKL_DEAD)}(&|$)`));
	const dialog = panel(page);
	await expect(dialog).toBeVisible();
	await expect(dialog.getByRole('heading', { level: 2 })).toHaveText(r.title);
	const links = dialog.getByRole('list', { name: /links/i }).getByRole('link');
	await expect(links.filter({ hasText: 'Original publisher' })).toHaveAttribute('href', r.url!);
	await expect(links.filter({ hasText: 'Archived copy on ORKL' })).toHaveAttribute('href', r.archive_url!);
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
		await rows.first().getByRole('link').first().click();
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
	// The live data has no undated report, because every report gets at least an ingest date,
	// so one is added to the index. The switch and the row are what is under test.
	const TITLE = 'A report with no date at all';
	const added = undated.length ? 0 : 1;
	if (added) {
		await page.route(INDEX, (route) =>
			route.fulfill({ json: withExtraRows(index, [{ id: 'synthetic-undated', title: TITLE, published: null }]) })
		);
	}
	const shownUndated = added ? TITLE : reports.find((r) => r.published == null)!.title;
	await open(page);
	const before = await shownCount(page);
	expect(before).toBe(dated.length + campaigns.length);
	await page.getByLabel(/include undated reports/i).check();
	await expect(page).toHaveURL(/[?&]undated=1/);
	await expect.poll(() => shownCount(page)).toBe(before + undated.length + added);
	// Undated rows sort last, so they are rendered once scrolled to.
	await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
	await expect(rowFor(page, shownUndated)).toBeVisible();
	await expect(rowFor(page, shownUndated).getByRole('cell').first()).toHaveText(/undated/i);

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
	const r = { ...reportById(PAPER_KEV), ...DEAD_NO_ARCHIVE };
	await editReport(page, PAPER_KEV, DEAD_NO_ARCHIVE);
	await open(page, `?report=${encodeURIComponent(PAPER_KEV)}`);
	const dialog = panel(page);
	const links = dialog.getByRole('list', { name: /links/i }).getByRole('link');
	await expect(links).toHaveCount(1);
	await expect(links.first()).toHaveAttribute('href', r.url!);
	await expect(dialog).toContainText(/original .*unreachable/i);
	// Its CVE is in KEV, and the panel says so.
	const cve = r.cves.find((c) => kevCves.has(c))!;
	await expect(dialog.getByRole('listitem').filter({ hasText: cve })).toContainText(/KEV/);
});

test('a report with no original URL offers the archive copy', async ({ page }) => {
	await editReport(page, ORKL_ANY, NO_URL);
	await open(page, `?report=${ORKL_ANY}`);
	const dialog = panel(page);
	const links = dialog.getByRole('list', { name: /links/i }).getByRole('link');
	await expect(links).toHaveCount(1);
	await expect(links.first()).toHaveAttribute('href', reportById(ORKL_ANY).archive_url!);
	await expect(dialog).toContainText(/no original publisher link is known/i);
});

test('an ORKL report shows its title, date and links, and no publisher', async ({ page }) => {
	const r = reportById(ORKL_LIVE);
	await open(page, `?report=${ORKL_LIVE}`);
	const dialog = panel(page);
	await expect(dialog.getByRole('heading', { level: 2 })).toHaveText(r.title);
	await expect(dialog.locator('time')).toHaveAttribute('datetime', r.published!);
	// Both the original and ORKL's archived copy are listed, original first (wave 3).
	const links = dialog.getByRole('list', { name: /links/i }).getByRole('link');
	await expect(links).toHaveCount(2);
	await expect(links.first()).toHaveAttribute('href', r.url!);
	await expect(links.nth(1)).toHaveAttribute('href', r.archive_url!);
	await expect(dialog.getByText('Publisher', { exact: true })).toHaveCount(0);
	await expect(dialog).toContainText(/link-only/i);
});

test('an ORKL report lists the actors, CVEs and techniques the pipeline found, and says where they came from', async ({
	page
}) => {
	// The table filters and searches on these, so a panel that hid them would disagree with
	// the list that opened it. They are shown together with a note that they are not ORKL's data.
	const r = reportById(ORKL_TAGGED);
	await open(page, `?report=${ORKL_TAGGED}`);
	const dialog = panel(page);
	for (const id of r.actors) await expect(dialog.getByRole('link', { name: nameOf(id), exact: true })).toBeVisible();
	for (const cve of r.cves) await expect(dialog).toContainText(cve);
	for (const tid of r.techniques) await expect(dialog).toContainText(tid);
	await expect(dialog).toContainText(/never\s+from ORKL's tags/i);
});

test("ORKL's actor tags never appear, in the table or the panel", async ({ page }) => {
	// Route a shard whose ORKL report carries names the registry left
	// unresolved. The contract keeps these empty for link-only rows, and the
	// site must not show them even if a build gets that wrong. The index has no
	// names at all, so a search cannot find them either.
	const TAG = 'Leaky Tag Panda';
	await editReport(page, ORKL_ANY, { actor_names_unresolved: [TAG] });
	await open(page, `?q=${encodeURIComponent(TAG)}`);
	expect(await shownCount(page)).toBe(0);
	await page.goto(`${EXPLORE}?report=${encodeURIComponent(ORKL_ANY)}`);
	await expect(panel(page)).toBeVisible();
	await expect(panel(page).getByRole('list', { name: /links/i })).toBeVisible();
	await expect(page.locator('body')).not.toContainText(TAG);
});

test('a campaign opens through ?campaign= with its span, actors and ATT&CK link', async ({ page }) => {
	const c = campaigns.find((x) => x.actors.length > 0 && x.techniques.length > 0 && /^[A-Za-z0-9 ]+$/.test(x.name))!;
	await open(page, `?q=${encodeURIComponent(c.name)}`);
	await rowFor(page, c.name).getByRole('link').first().click();
	await expect(page).toHaveURL(new RegExp(`[?&]campaign=${c.id}`));
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
		`https://attack.mitre.org/campaigns/${c.id}/`
	);
});

test('an unknown ?report= says it is not in the data', async ({ page }) => {
	await open(page, '?report=zzz-not-a-report');
	await expect(panel(page)).toContainText(/not in the current data/i);
});

test('the panel takes focus, closes on Escape, clears ?report= and returns focus to the row', async ({ page }) => {
	const r = reportById(ORKL_DEAD);
	await open(page, byTitle(ORKL_DEAD));
	const link = rowFor(page, r.title).getByRole('link').first();
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
	// Every report of the actor whose alias this is must match, and so may a report whose
	// title says "Fancy Bear" for some other actor, so the count is a floor, not an equality.
	const expected = dated.filter((r) => r.actors.includes('G0007')).length;
	await expect.poll(() => shownCount(page)).toBeGreaterThanOrEqual(expected);
	// Narrowed to the actor, the rows shown are the ones its alias found.
	await open(page, '?q=fancy+bear&actor=G0007');
	const rows = bodyRows(page);
	for (let i = 0; i < 5; i++) await expect(rows.nth(i)).toContainText('APT28');
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
	const extras = Array.from({ length: N }, (_, i) => ({
		id: `synthetic-${i}`,
		title: `Synthetic report ${i}`,
		published: `2025-${String((i % 12) + 1).padStart(2, '0')}-15`,
		organisation: 'Fieldnote DFIR',
		actors: ['G0032']
	}));
	await page.route(INDEX, (route) => route.fulfill({ json: withExtraRows(index, extras) }));
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

test('with scripts blocked, the prerendered page explains that the table needs them', async ({ page }) => {
	await page.route('**/*.js', (r) => r.abort());
	await page.goto(EXPLORE);
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Explore');
	await expect(status(page)).toContainText(/scripts/i);
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
