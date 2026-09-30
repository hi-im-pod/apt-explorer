import { readFileSync } from 'node:fs';
import { test, expect, type Page } from '@playwright/test';
import type { Actor, ActorsIndex, Report } from '../src/lib/data/types';
import { countryName } from '../src/routes/actors/actors';
import {
	FIRST_ALIASES,
	FIRST_CHIPS,
	FIRST_REPORTS,
	FIRST_TECHNIQUES,
	ledeFor,
	linkNote,
	NAME_SOURCES,
	otherSources,
	reportLinks
} from '../src/routes/actors/[id]/profile';
import { openSynthIndex, synthActor, synthReports, SYNTH_ACTORS, SYNTH_REPORTS } from './actors-synth';

// Expectations come from the same data/ the site is built from, so the tests
// check that the page shows what the data says rather than a copy of it.
const DATA = new URL('../../data/', import.meta.url);
const readJson = <T>(path: string): T => JSON.parse(readFileSync(new URL(path, DATA), 'utf8')) as T;
const index = readJson<ActorsIndex>('actors/index.json');
const actorFile = (id: string) => readJson<Actor>(`actors/${id}.json`);
const allReports: Report[] = [
	...readJson<{ report_years: number[] }>('build.json').report_years.flatMap((y) =>
		readJson<Report[]>(`reports/${y}.json`)
	),
	...readJson<Report[]>('reports/undated.json')
];

const themes = ['light', 'dark', 'apt'] as const;
const ACTORS = '/apt-explorer/actors/';
const profile = (id: string) => `${ACTORS}${id}/`;

// The data's extreme cases, found from the data so the tests follow it.
const busiest = [...index].sort((a, b) => b.report_count - a.report_count)[0];
const mostCves = [...index].sort((a, b) => actorFile(b.id).cves.length - actorFile(a.id).cves.length)[0];
const empty = index.find((a) => a.report_count === 0)!;
// The live data has no alias this long, and the synthesized busy profile below carries one in
// every theme, so the real-data check only runs when a source does publish such an alias.
const longAlias = index.find((a) => a.aliases.some((x) => x.length > 60 && !x.includes(' ')));
const conflicted = index.find((a) => actorFile(a.id).conflicts.some((c) => c.field === 'origin'))!;

async function useTheme(page: Page, t: string) {
	await page.addInitScript((th) => {
		try {
			localStorage.setItem('theme', th);
		} catch {}
	}, t);
}

/** Where a link really goes: prerendered hrefs may be relative. */
const target = (page: Page, selector: ReturnType<Page['locator']>) =>
	selector.evaluate((a) => {
		const u = new URL((a as HTMLAnchorElement).href);
		return u.pathname + u.search + u.hash;
	});

/**
 * No horizontal scroll, checked twice over: the document must not be wider
 * than the screen, and no box inside main may hide content that overflows
 * it. The first check alone misses a box with overflow hidden or auto that
 * clips its content, which is the other way a long alias breaks a layout.
 * Visually hidden labels clip by design and are skipped.
 */
async function expectFitsWidth(page: Page) {
	const report = await page.evaluate(() => {
		const doc = document.documentElement;
		const clipped = [...document.querySelectorAll('main, main *')]
			.filter((e) => !e.closest('.visually-hidden'))
			.filter((e) => e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflowX !== 'visible')
			.map((e) => `${e.tagName}.${e.className}`);
		return { scroll: doc.scrollWidth, client: doc.clientWidth, clipped };
	});
	expect(report.clipped, 'boxes that clip their content').toEqual([]);
	expect(report.scroll, 'document scroll width').toBeLessThanOrEqual(report.client);
}

/** Every h2 in main must have something under it besides itself. */
async function expectNoEmptySections(page: Page) {
	const empties = await page.evaluate(() =>
		[...document.querySelectorAll('main h2')]
			.filter((h) => {
				const section = h.closest('section');
				if (!section) return true;
				const rest = (section.textContent ?? '').replace(h.textContent ?? '', '').trim();
				return rest.length === 0;
			})
			.map((h) => h.textContent)
	);
	expect(empties).toEqual([]);
}

// ---------------------------------------------------------------------------
// The index

test('the index lists every actor, each linking to its profile', async ({ page }) => {
	await page.goto(ACTORS);
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Actors');
	const rows = page.getByRole('list', { name: 'Actors' }).getByRole('listitem');
	await expect(rows).toHaveCount(index.length);
	const link = rows.getByRole('link', { name: busiest.name, exact: true });
	expect(await target(page, link)).toBe(profile(busiest.id));
});

test('the index is sorted by recent reporting, and the sort can change', async ({ page }) => {
	await page.goto(ACTORS);
	const names = () => page.getByRole('list', { name: 'Actors' }).locator(':scope > li a.name').allInnerTexts();
	const byRecent = [...index].sort((a, b) =>
		a.last_reported === b.last_reported
			? a.name.toLowerCase() < b.name.toLowerCase()
				? -1
				: 1
			: a.last_reported === null
				? 1
				: b.last_reported === null
					? -1
					: a.last_reported < b.last_reported
						? 1
						: -1
	);
	expect(await names()).toEqual(byRecent.map((a) => a.name));
	await page.getByLabel('Sort by').selectOption('reports');
	expect((await names())[0]).toBe(busiest.name);
	await page.getByLabel('Sort by').selectOption('name');
	const sorted = await names();
	expect(sorted).toEqual([...sorted].sort((a, b) => (a.toLowerCase() < b.toLowerCase() ? -1 : 1)));
});

test('search narrows the list by name, alias or ID, and says which alias matched', async ({ page }) => {
	await page.goto(ACTORS);
	const rows = page.getByRole('list', { name: 'Actors' }).getByRole('listitem');
	const search = page.getByRole('searchbox', { name: /search/i });
	await search.fill('fancy-bear');
	await expect(rows).toHaveCount(1);
	await expect(rows.first()).toContainText('APT28');
	await expect(page.getByRole('status')).toContainText(`1 of ${index.length.toLocaleString('en-US')}`);
	await search.fill('g0032');
	await expect(rows).toHaveCount(1);
	await expect(rows.first()).toContainText('Lazarus Group');
	await search.fill('no actor is called this');
	await expect(rows).toHaveCount(0);
	await expect(page.getByText(/no actor matches/i)).toBeVisible();
	await search.fill('');
	await expect(rows).toHaveCount(index.length);
});

test(`the index handles ${SYNTH_ACTORS} actors, and search narrows them`, async ({ page }) => {
	await openSynthIndex(page);
	const rows = page.getByRole('list', { name: 'Actors' }).getByRole('listitem');
	const search = page.getByRole('searchbox', { name: /search/i });
	// "Synthetic Actor 01x" matches ten actors by name: 010 to 019.
	await search.fill('synthetic actor 01');
	await expect(rows).toHaveCount(10);
	// An alias only one actor has.
	await search.fill('cluster 042');
	await expect(rows).toHaveCount(1);
	await expect(rows.first()).toContainText('Synthetic Actor 042');
	await expect(rows.first()).toContainText(/matches the alias/i);
});

for (const t of themes) {
	test(`at 375px in ${t}, the index with ${SYNTH_ACTORS} long-aliased actors fits the screen`, async ({ page }) => {
		await page.setViewportSize({ width: 375, height: 800 });
		await useTheme(page, t);
		await openSynthIndex(page);
		await expect(page.locator('html')).toHaveAttribute('data-theme', t);
		await expectFitsWidth(page);
	});
}

// ---------------------------------------------------------------------------
// Profiles from the sample data

test(`a direct load of the busiest actor shows aliases with badges, a timeline and reports`, async ({ page }) => {
	const a = actorFile(busiest.id);
	await page.goto(profile(busiest.id));
	await expect(page.getByRole('heading', { level: 1 })).toHaveText(a.name);

	// The first names show at once; the rest sit behind "Show all" and are checked once it is open.
	const aliases = page.locator('.alias-list > li');
	await expect(page.getByRole('list', { name: 'Names and who uses them' }).getByRole('listitem')).toHaveCount(
		Math.min(a.aliases.length, FIRST_ALIASES)
	);
	await expect(aliases).toHaveCount(a.aliases.length);
	if (a.aliases.length > FIRST_ALIASES) await page.getByText(/show all [\d,]+ names/i).click();
	for (const [i, alias] of a.aliases.entries()) {
		const row = aliases.nth(i);
		await expect(row).toContainText(alias.value);
		const badges = row.getByRole('link');
		await expect(badges).toHaveCount(alias.sources.length);
		for (const b of await badges.all()) await expect(b).toBeVisible();
	}
	const first = a.aliases[0].sources;
	const firstSource = NAME_SOURCES.find((n) => first.includes(n.key))?.key ?? otherSources(first)[0];
	expect(await target(page, aliases.first().getByRole('link').first())).toBe(
		`/apt-explorer/about/#source-${firstSource}`
	);

	const bars = page.getByRole('list', { name: 'Dated reports per quarter' }).locator('.bar');
	await expect(bars).toHaveCount(a.timeline.filter((p) => p.count > 0).length);
	for (const bar of await bars.all()) {
		const box = await bar.boundingBox();
		expect(box?.height ?? 0).toBeGreaterThan(0);
	}

	// The newest reports are listed and the rest wait behind "Show all", so every row
	// exists in the page but only the first ten are visible to begin with.
	const reports = page.getByRole('list', { name: 'Reports', exact: true }).getByRole('listitem');
	await expect(page.locator('#reports li.report')).toHaveCount(a.reports.length);
	await expect(reports).toHaveCount(Math.min(a.reports.length, FIRST_REPORTS));
	const newest = allReports.find((r) => r.id === a.reports[0])!;
	await expect(reports.first()).toContainText(newest.title);
	expect(await target(page, reports.first().getByRole('link', { name: newest.title, exact: true }))).toBe(
		new URL(newest.url!).pathname
	);
});

test('report links open the original first, and the archive when the original is dead', async ({ page }) => {
	const a = actorFile(busiest.id);
	await page.goto(profile(busiest.id));
	const items = page.locator('#reports li.report');
	// The first ten, and every report whose original is dead, wherever it sits in the list.
	const byId = new Map(allReports.map((r) => [r.id, r]));
	const check = a.reports
		.map((id, i) => ({ id, i, r: byId.get(id)! }))
		.filter(({ i, r }) => i < FIRST_REPORTS || r.url_ok === false);
	expect(check.some(({ r }) => r.url_ok === false && r.archive_url), 'a dead original with an archive copy').toBe(true);
	for (const { id, i, r } of check) {
		const title = items.nth(i).locator('a', { hasText: r.title }).first();
		const href = await title.evaluate((el) => (el as HTMLAnchorElement).href);
		const expected = r.url && r.url_ok === false && r.archive_url ? r.archive_url : (r.url ?? r.archive_url);
		expect(href, r.title).toBe(expected);
		// Every report opens in Explore's detail panel too.
		const details = items.nth(i).locator('a', { hasText: /details/i });
		expect(await target(page, details)).toBe(`/apt-explorer/explore/?report=${encodeURIComponent(id)}`);
	}
});

test('a mirror in the url field is named a mirror on the profile, never the original', async ({ page }) => {
	const byId = new Map(allReports.map((r) => [r.id, r]));
	// The busiest profile lists no mirror among its first reports, so the test takes the busiest
	// one that does, found from the data.
	const withMirror = [...index]
		.sort((x, y) => y.report_count - x.report_count)
		.find((x) =>
			actorFile(x.id)
				.reports.slice(0, FIRST_REPORTS)
				.some((id) => reportLinks(byId.get(id)!).primary?.kind === 'copy')
		)!;
	const a = actorFile(withMirror.id);
	await page.goto(profile(withMirror.id));
	const items = page.locator('#reports li.report');
	let mirrors = 0;
	for (const [i, id] of a.reports.slice(0, FIRST_REPORTS).entries()) {
		const r = byId.get(id)!;
		const expected = reportLinks(r);
		const text = await items.nth(i).locator('.report-links').innerText();
		if (expected.primary?.kind === 'copy') mirrors += 1;
		// Every visible label is the one the helper gives for that link's host.
		if (expected.secondary) expect(text, r.title).toContain(expected.secondary.label);
		const note = linkNote(expected);
		if (note) expect(text, r.title).toContain(note);
		// An original label appears only for a link the helper calls the original.
		const hasOriginal = [expected.primary, expected.secondary].some((l) => l?.kind === 'original');
		if (!hasOriginal) expect(text, r.title).not.toMatch(/original (link|publisher)/i);
	}
	expect(mirrors, 'the chosen profile lists at least one report whose link is a mirror').toBeGreaterThan(0);
});

test('an actor with no reports has no reports or timeline section', async ({ page }) => {
	await page.goto(profile(empty.id));
	await expect(page.getByRole('heading', { level: 1 })).toHaveText(empty.name);
	await expect(page.getByRole('heading', { name: /^reports/i })).toHaveCount(0);
	await expect(page.getByRole('heading', { name: /timeline/i })).toHaveCount(0);
	await expect(page.getByRole('list', { name: 'Reports', exact: true })).toHaveCount(0);
	await expect(page.getByRole('main')).toContainText(/no published report/i);
	await expectNoEmptySections(page);
});

test('every section on a spread of profiles has content', async ({ page }) => {
	// Loading all 1,000 or so profiles one at a time would outlast the test timeout, so every
	// tenth one is opened, along with the three extremes the other tests use.
	test.setTimeout(120_000);
	const picked = new Set([busiest, empty, conflicted, ...index.filter((_, i) => i % 10 === 0)]);
	for (const a of picked) {
		await page.goto(profile(a.id));
		await expect(page.getByRole('heading', { level: 1 })).toHaveText(a.name);
		await expectNoEmptySections(page);
	}
});

for (const t of themes) {
	if (longAlias)
		test(`at 375px in ${t}, a profile with a ${Math.max(...longAlias.aliases.map((x) => x.length))}-character alias fits the screen`, async ({
			page
		}) => {
			await page.setViewportSize({ width: 375, height: 800 });
			await useTheme(page, t);
			await page.goto(profile(longAlias.id));
			await expect(page.locator('html')).toHaveAttribute('data-theme', t);
			const alias = longAlias.aliases.find((x) => x.length > 60)!;
			await expect(page.getByText(alias, { exact: true }).first()).toBeVisible();
			await expectFitsWidth(page);
		});

	test(`at 375px in ${t}, the sample index fits the screen`, async ({ page }) => {
		await page.setViewportSize({ width: 375, height: 800 });
		await useTheme(page, t);
		await page.goto(ACTORS);
		await expectFitsWidth(page);
	});
}

test('a conflict names every source and value', async ({ page }) => {
	const c = actorFile(conflicted.id).conflicts.find((x) => x.field === 'origin')!;
	await page.goto(profile(conflicted.id));
	const note = page.getByRole('note', { name: new RegExp(c.field) });
	await expect(note).toBeVisible();
	for (const v of c.values) {
		await expect(note.getByRole('link', { name: new RegExp({ misp: 'MISP', etda: 'ETDA', malpedia: 'Malpedia' }[v.source] ?? v.source) })).toBeVisible();
	}
	// Origin codes are shown as country names.
	for (const v of c.values) await expect(note).toContainText(countryName(v.value));
});

test('running text names MITRE ATT&CK with the ® at its first mention', async ({ page }) => {
	// Badges and headings are labels and carry no sign; the first sentence
	// that names ATT&CK does, as MITRE's terms ask.
	for (const path of [ACTORS, profile(busiest.id), profile(empty.id)]) {
		await page.goto(path);
		const first = await page.evaluate(
			() => [...document.querySelectorAll('main p')]
					.map((p) => (p.textContent ?? '').replace(/\s+/g, ' '))
					.find((t) => t.includes('ATT&CK')) ?? ''
		);
		expect(first, path).toContain('MITRE ATT&CK®');
	}
});

test('claimed targets carry their actor-level label', async ({ page }) => {
	await page.goto(profile(busiest.id));
	await expect(page.getByRole('heading', { name: 'Claimed targets (actor-level, per source)' })).toBeVisible();
});

test('with scripts blocked, the prerendered profile still reads', async ({ page }) => {
	await page.route('**/*.js', (r) => r.abort());
	const a = actorFile(busiest.id);
	await page.goto(profile(busiest.id));
	await expect(page.getByRole('heading', { level: 1 })).toHaveText(a.name);
	// "Show all" is a native <details>, so it opens without scripts.
	for (const summary of await page.locator('details.more > summary').all()) await summary.click();
	for (const alias of a.aliases) await expect(page.getByText(alias.value, { exact: true }).first()).toBeVisible();
	await expect(page.locator('#reports li.report')).toHaveCount(a.reports.length);
	const bar = page.getByRole('list', { name: 'Dated reports per quarter' }).locator('.bar').first();
	expect((await bar.boundingBox())?.height ?? 0).toBeGreaterThan(0);
});

test('the profile links back to the index under the base path', async ({ page }) => {
	await page.goto(profile(busiest.id));
	const back = page.getByRole('main').getByRole('link', { name: /all actors/i });
	expect(await target(page, back)).toBe(ACTORS);
	await expect(page.getByRole('navigation').getByRole('link', { name: 'Actors', exact: true })).toHaveAttribute(
		'aria-current',
		'page'
	);
});

// ---------------------------------------------------------------------------
// The headline, the facts and the capped lists

test('the headline carries a lede and facts built from the actor file', async ({ page }) => {
	const a = actorFile(busiest.id);
	await page.goto(profile(busiest.id));
	const lede = ledeFor(a);
	expect(lede).not.toBeNull();
	await expect(page.locator('.actor-head .lede')).toHaveText(lede!);
	const facts = page.locator('.facts > div');
	const fact = (name: string) => facts.filter({ has: page.getByText(name, { exact: true }) }).locator('dd');
	await expect(fact('Reports')).toHaveText(a.reports.length.toLocaleString('en-US'));
	await expect(fact('Known CVEs')).toHaveText(a.cves.length.toLocaleString('en-US'));
	await expect(fact('Techniques in ATT&CK')).toHaveText(a.techniques_documented.length.toLocaleString('en-US'));
	await expect(fact('Last reported')).toBeVisible();
});

test('the CVE list shows twelve, and "Show all" opens the rest in place', async ({ page }) => {
	const a = actorFile(mostCves.id);
	expect(a.cves.length, 'the data has an actor with more than twelve CVEs').toBeGreaterThan(FIRST_CHIPS);
	await page.goto(profile(mostCves.id));
	const all = page.locator('#cves li');
	const firstList = page.getByRole('list', { name: 'CVEs named in reports' }).getByRole('listitem');
	await expect(all).toHaveCount(a.cves.length);
	await expect(firstList).toHaveCount(FIRST_CHIPS);
	await expect(all.last()).toBeHidden();

	const summary = page.locator('#cves details.more > summary');
	await expect(summary).toHaveAccessibleName(`Show all ${a.cves.length.toLocaleString('en-US')} CVEs`);
	const top = () =>
		page.evaluate(() => {
			const y = (sel: string) => document.querySelector(sel)!.getBoundingClientRect().top + scrollY;
			return { heading: y('#cves-heading'), summary: y('#cves details.more > summary') };
		});
	const before = await top();
	// Keyboard first: the control is a real button-like summary that keeps focus when it opens.
	await summary.focus();
	await page.keyboard.press('Enter');
	await expect(page.locator('#cves details.more')).toHaveAttribute('open', '');
	await expect(summary).toBeFocused();
	await expect(summary).toHaveAccessibleName('Show fewer');
	await expect(all.last()).toBeVisible();
	const after = await top();
	expect(after.heading, 'the heading above does not move').toBe(before.heading);
	expect(after.summary, 'the control does not move').toBe(before.summary);

	await page.keyboard.press('Enter');
	await expect(all.last()).toBeHidden();
	await expect(summary).toBeFocused();
});

test('the busy synthesized profile caps every long list and opens each in place', async ({ page }) => {
	await openSynthIndex(page);
	await page.getByRole('link', { name: 'Busy Synthetic Actor', exact: true }).click();
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Busy Synthetic Actor');
	const actor = synthActor(synthReports());
	const visible = (selector: string) => page.locator(selector).filter({ visible: true });
	await expect(visible('.alias-list > li')).toHaveCount(FIRST_ALIASES);
	await expect(visible('#cves li')).toHaveCount(FIRST_CHIPS);
	await expect(visible('.tech > li')).toHaveCount(FIRST_TECHNIQUES);
	await expect(visible('#reports li.report')).toHaveCount(FIRST_REPORTS);
	// One control per capped list: names, techniques, techniques listed by ATT&CK, CVEs, reports,
	// countries, sectors and malware.
	await expect(page.locator('details.more')).toHaveCount(8);
	for (const s of await page.locator('details.more > summary').all()) {
		const y = await s.evaluate((el) => el.getBoundingClientRect().top + scrollY);
		await s.click();
		expect(await s.evaluate((el) => el.getBoundingClientRect().top + scrollY)).toBe(y);
	}
	await expect(visible('.alias-list > li')).toHaveCount(actor.aliases.length);
	await expect(visible('#cves li')).toHaveCount(actor.cves.length);
});

test('a profile with short lists has no "Show all" control', async ({ page }) => {
	const short = index.find((a) => {
		const f = actorFile(a.id);
		return (
			f.aliases.length <= FIRST_ALIASES &&
			f.cves.length <= FIRST_CHIPS &&
			f.reports.length <= FIRST_REPORTS &&
			f.techniques_reported.length <= FIRST_TECHNIQUES &&
			f.techniques_documented.length <= FIRST_CHIPS &&
			f.malware.length <= FIRST_CHIPS
		);
	})!;
	await page.goto(profile(short.id));
	await expect(page.getByRole('heading', { level: 1 })).toHaveText(short.name);
	await expect(page.locator('details.more')).toHaveCount(0);
	await expectNoEmptySections(page);
});

// ---------------------------------------------------------------------------
// Unknown actors

test('an unknown actor ID shows the not-found page', async ({ page }) => {
	await page.goto(profile('zzz-unknown'));
	await expect(page.getByRole('heading', { name: /not found/i })).toBeVisible();
});

test('an unknown actor ID served the way Pages serves it shows the not-found page', async ({ page }) => {
	// Pages answers a path it has no file for with build/404.html and status
	// 404, and the app then asks for the route's __data.json, which is also
	// missing. vite preview would render both on the server instead, so
	// answer both requests the way Pages does.
	const fallback = readFileSync(new URL('../build/404.html', import.meta.url), 'utf8');
	await page.route('**/apt-explorer/actors/zzz-unknown/', (r) =>
		r.fulfill({ status: 404, contentType: 'text/html', body: fallback })
	);
	await page.route('**/apt-explorer/actors/zzz-unknown/__data.json*', (r) =>
		r.fulfill({ status: 404, contentType: 'text/html', body: fallback })
	);
	await page.goto(profile('zzz-unknown'));
	await expect(page.getByRole('heading', { name: /not found/i })).toBeVisible();
	await expect(page.getByRole('navigation')).toBeVisible();
});

// ---------------------------------------------------------------------------
// A synthesized busy actor

test(`a profile with ${SYNTH_REPORTS} reports lists them all and draws every quarter`, async ({ page }) => {
	await openSynthIndex(page);
	await page.getByRole('link', { name: 'Busy Synthetic Actor', exact: true }).click();
	await expect(page).toHaveURL(/\/actors\/synth-busy\/$/);
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Busy Synthetic Actor');
	const reports = page.getByRole('list', { name: 'Reports', exact: true }).getByRole('listitem');
	// Hidden rows behind "show all" still exist in the page.
	await expect(page.locator('#reports li.report')).toHaveCount(SYNTH_REPORTS);
	await expect(reports.first()).toBeVisible();
	const actor = synthActor(synthReports());
	const bars = page.getByRole('list', { name: 'Dated reports per quarter' }).locator('.bar');
	await expect(bars).toHaveCount(actor.timeline.length);
	for (const bar of await bars.all()) expect((await bar.boundingBox())?.height ?? 0).toBeGreaterThan(0);
	await expect(page.getByRole('main')).toContainText('10 undated reports are not shown');
	await expect(page.locator('.alias-list > li')).toHaveCount(actor.aliases.length);
});

for (const w of [1280, 375]) {
	for (const t of themes) {
		test(`at ${w}px in ${t}, the synthesized busy profile fits the screen, opened and closed`, async ({ page }) => {
			await page.setViewportSize({ width: w, height: 900 });
			await useTheme(page, t);
			await openSynthIndex(page);
			await page.getByRole('link', { name: 'Busy Synthetic Actor', exact: true }).click();
			await expect(page.getByRole('heading', { level: 1 })).toHaveText('Busy Synthetic Actor');
			await expectFitsWidth(page);
			await expectNoEmptySections(page);
			for (const summary of await page.locator('details.more > summary').all()) await summary.click();
			await expect(page.locator('#reports li.report').last()).toBeVisible();
			await expect(page.locator('details.more[open]')).toHaveCount(await page.locator('details.more').count());
			await expectFitsWidth(page);
		});
	}
}

// ---------------------------------------------------------------------------

test('the actors pages load without console errors', async ({ page }) => {
	const errors: string[] = [];
	page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
	page.on('pageerror', (e) => errors.push(e.message));
	for (const path of [ACTORS, profile(busiest.id), profile(empty.id), profile(conflicted.id)]) {
		await page.goto(path);
		await page.waitForLoadState('networkidle');
	}
	expect(errors).toEqual([]);
});
