import { test, expect } from '@playwright/test';
const themes = ['light', 'dark', 'apt'] as const;

for (const w of [1280, 375]) for (const t of themes) {
  test(`shell renders in ${t} at ${w}px`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: 900 });
    await page.addInitScript(th => { try { localStorage.setItem('theme', th); } catch {} }, t);
    await page.goto('/apt-explorer/about/');
    await expect(page.locator('html')).toHaveAttribute('data-theme', t);
    const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    expect(bg).not.toBe('rgba(0, 0, 0, 0)');
    const noHScroll = await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);
    expect(noHScroll).toBe(true);
    await expect(page.getByRole('navigation')).toBeVisible();
  });
}

test('unknown path gets the styled not-found page', async ({ page }) => {
  await page.goto('/apt-explorer/definitely/not/here/');
  await expect(page.getByRole('heading', { name: /not found/i })).toBeVisible();
});

test('theme switcher changes computed colours and persists', async ({ page }) => {
  await page.goto('/apt-explorer/about/');
  const before = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await page.getByRole('button', { name: /theme/i }).click();
  await page.getByRole('menuitemradio', { name: /apt/i }).click();
  const after = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(after).not.toBe(before);
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'apt');
});

// ---------------------------------------------------------------------------
// Beyond the plan's cases.

const bodyBg = (page: import('@playwright/test').Page) =>
	page.evaluate(() => getComputedStyle(document.body).backgroundColor);

test('each theme paints a different background', async ({ page }) => {
	// data-theme being set proves nothing if the CSS for it never matches.
	const seen = new Set<string>();
	for (const t of themes) {
		await page.addInitScript((th) => {
			try {
				localStorage.setItem('theme', th);
			} catch {}
		}, t);
		await page.goto('/apt-explorer/about/');
		seen.add(await bodyBg(page));
	}
	expect(seen.size).toBe(3);
});

test('with no stored choice the page follows the OS colour scheme', async ({ browser }) => {
	for (const scheme of ['light', 'dark'] as const) {
		const ctx = await browser.newContext({ colorScheme: scheme });
		const page = await ctx.newPage();
		await page.goto('/apt-explorer/about/');
		await expect(page.locator('html')).not.toHaveAttribute('data-theme', /.*/);
		const bg = await bodyBg(page);
		// Light is #f8f6fb and dark is #16121d; see app.css.
		expect(bg).toBe(scheme === 'light' ? 'rgb(248, 246, 251)' : 'rgb(22, 18, 29)');
		await ctx.close();
	}
});

test('a stored value that is not a theme is ignored, not applied', async ({ page }) => {
	await page.addInitScript(() => {
		try {
			localStorage.setItem('theme', '"><img src=x>');
		} catch {}
	});
	await page.goto('/apt-explorer/about/');
	await expect(page.locator('html')).not.toHaveAttribute('data-theme', /.*/);
	expect(await bodyBg(page)).toBe('rgb(248, 246, 251)');
});

test('the theme menu works from the keyboard and reports the checked theme', async ({ page }) => {
	await page.goto('/apt-explorer/about/');
	const button = page.getByRole('button', { name: /theme/i });
	await expect(button).toHaveAttribute('aria-haspopup', 'menu');
	await button.focus();
	await page.keyboard.press('Enter');
	const menu = page.getByRole('menu');
	await expect(menu).toBeVisible();
	await expect(button).toHaveAttribute('aria-expanded', 'true');
	// Focus lands on the checked item (light, with the default OS scheme).
	await expect(page.getByRole('menuitemradio', { name: /light/i })).toBeFocused();
	await page.keyboard.press('ArrowDown');
	await expect(page.getByRole('menuitemradio', { name: /dark/i })).toBeFocused();
	await page.keyboard.press('Enter');
	await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
	await expect(menu).toBeHidden();
	await expect(button).toBeFocused();

	await page.keyboard.press('Enter');
	await expect(page.getByRole('menuitemradio', { name: /dark/i })).toHaveAttribute('aria-checked', 'true');
	await expect(page.getByRole('menuitemradio', { name: /light/i })).toHaveAttribute('aria-checked', 'false');
	await page.keyboard.press('Escape');
	await expect(menu).toBeHidden();
	await expect(button).toBeFocused();
});

test('the theme menu closes on a click outside it', async ({ page }) => {
	await page.goto('/apt-explorer/about/');
	await page.getByRole('button', { name: /theme/i }).click();
	await expect(page.getByRole('menu')).toBeVisible();
	await page.getByRole('heading', { level: 1 }).click();
	await expect(page.getByRole('menu')).toBeHidden();
});

test('pages load without console errors', async ({ page }) => {
	const errors: string[] = [];
	page.on('console', (m) => m.type() === 'error' && errors.push(m.text()));
	page.on('pageerror', (e) => errors.push(e.message));
	for (const path of ['/apt-explorer/', '/apt-explorer/about/']) {
		await page.goto(path);
		await page.waitForLoadState('networkidle');
	}
	expect(errors).toEqual([]);
});

test('header links stay under the base path', async ({ page }) => {
	await page.goto('/apt-explorer/');
	const nav = page.getByRole('navigation');
	for (const [name, path] of [
		['Explore', '/apt-explorer/explore/'],
		['Actors', '/apt-explorer/actors/'],
		['Trends', '/apt-explorer/trends/'],
		['About', '/apt-explorer/about/']
	]) {
		const href = await nav.getByRole('link', { name, exact: true }).evaluate((a) => (a as HTMLAnchorElement).href);
		expect(new URL(href).pathname).toBe(path);
	}
	await nav.getByRole('link', { name: 'About', exact: true }).click();
	await expect(page).toHaveURL(/\/apt-explorer\/about\/$/);
	await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
});

test('the current page is marked in the header', async ({ page }) => {
	await page.goto('/apt-explorer/about/');
	const about = page.getByRole('navigation').getByRole('link', { name: 'About', exact: true });
	await expect(about).toHaveAttribute('aria-current', 'page');
});

test('the footer shows the build date and links to sources and licences', async ({ page }) => {
	await page.goto('/apt-explorer/');
	const footer = page.getByRole('contentinfo');
	// build.json in the sample says 2026-09-28T03:21:05Z.
	await expect(footer.locator('time')).toHaveAttribute('datetime', '2026-09-28T03:21:05Z');
	await expect(footer.locator('time')).toHaveText('28 September 2026');
	await footer.getByRole('link', { name: /sources and licences/i }).click();
	await expect(page).toHaveURL(/\/apt-explorer\/about\/$/);
});

test('the home page lists every source with its health', async ({ page }) => {
	await page.goto('/apt-explorer/');
	const items = page.getByRole('list', { name: /source health/i }).getByRole('listitem');
	await expect(items).toHaveCount(8);
	// dfir is the stale source in the sample.
	await expect(items.filter({ hasText: 'The DFIR Report' })).toContainText(/stale/i);
	await expect(page.getByRole('link', { name: /explore/i }).first()).toBeVisible();
});

test('the 404.html that Pages serves renders the styled not-found page', async ({ page }) => {
	// vite preview answers an unknown path by rendering the error page on the
	// server, so the plain not-found test never touches build/404.html. Pages
	// serves that file, with status 404, for any path it has no file for, so
	// serve it the same way here.
	const { readFileSync } = await import('node:fs');
	const fallback = readFileSync(new URL('../build/404.html', import.meta.url), 'utf8');
	const deep = '/apt-explorer/actors/zzz-unknown/deeper/';
	await page.route(`**${deep}`, (r) =>
		r.fulfill({ status: 404, contentType: 'text/html', body: fallback })
	);
	const failed: string[] = [];
	page.on('requestfailed', (r) => failed.push(`failed ${r.url()}`));
	page.on('response', (r) => {
		if (r.status() >= 400 && !r.url().endsWith(deep)) failed.push(`${r.status()} ${r.url()}`);
	});
	await page.goto(deep);
	await expect(page.getByRole('heading', { name: /not found/i })).toBeVisible();
	await expect(page.getByRole('navigation')).toBeVisible();
	expect(await bodyBg(page)).not.toBe('rgba(0, 0, 0, 0)');
	// Links on the fallback page still point under the base path, even though
	// the page was served from a path several levels deep.
	const about = page.getByRole('navigation').getByRole('link', { name: 'About', exact: true });
	expect(new URL(await about.evaluate((a) => (a as HTMLAnchorElement).href)).pathname).toBe(
		'/apt-explorer/about/'
	);
	expect(failed).toEqual([]);
});

test('the not-found page is styled and keeps the site header', async ({ page }) => {
	await page.goto('/apt-explorer/definitely/not/here/');
	await expect(page.getByRole('heading', { level: 1 })).toHaveText(/not found/i);
	await expect(page.getByRole('navigation')).toBeVisible();
	expect(await bodyBg(page)).not.toBe('rgba(0, 0, 0, 0)');
	const home = page.getByRole('main').getByRole('link', { name: /home page/i });
	expect(new URL(await home.evaluate((a) => (a as HTMLAnchorElement).href)).pathname).toBe(
		'/apt-explorer/'
	);
});
