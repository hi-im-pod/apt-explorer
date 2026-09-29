import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { get } from 'svelte/store';
import { readFileSync } from 'node:fs';

// theme.ts is imported with no document or localStorage in scope. That is the
// prerender situation, and importing it must not throw there.
import { THEMES, initTheme, setTheme, theme } from './theme';

type Html = { dataset: Record<string, string | undefined> };

function stubBrowser(opts: { stored?: string | null; storage?: 'ok' | 'throws'; osDark?: boolean }) {
	const html: Html = { dataset: {} };
	const saved = new Map<string, string>();
	if (opts.stored != null) saved.set('theme', opts.stored);
	const storage =
		opts.storage === 'throws'
			? {
					getItem: () => {
						throw new DOMException('denied', 'SecurityError');
					},
					setItem: () => {
						throw new DOMException('denied', 'SecurityError');
					}
				}
			: {
					getItem: (k: string) => saved.get(k) ?? null,
					setItem: (k: string, v: string) => void saved.set(k, v)
				};
	vi.stubGlobal('document', { documentElement: html });
	vi.stubGlobal('localStorage', storage);
	vi.stubGlobal('matchMedia', (q: string) => ({
		matches: q.includes('dark') ? !!opts.osDark : false,
		addEventListener: () => {},
		removeEventListener: () => {}
	}));
	return { html, saved };
}

beforeEach(() => vi.unstubAllGlobals());
afterEach(() => vi.unstubAllGlobals());

describe('theme store', () => {
	it('offers exactly the three themes', () => {
		expect(THEMES).toEqual(['light', 'dark', 'apt']);
	});

	it('setTheme sets the attribute, the store and localStorage', () => {
		const { html, saved } = stubBrowser({});
		setTheme('apt');
		expect(html.dataset.theme).toBe('apt');
		expect(get(theme)).toBe('apt');
		expect(saved.get('theme')).toBe('apt');
	});

	it('setTheme still applies the theme when storage is blocked', () => {
		const { html } = stubBrowser({ storage: 'throws' });
		expect(() => setTheme('dark')).not.toThrow();
		expect(html.dataset.theme).toBe('dark');
		expect(get(theme)).toBe('dark');
	});

	it('initTheme applies a stored choice', () => {
		const { html } = stubBrowser({ stored: 'dark' });
		initTheme();
		expect(html.dataset.theme).toBe('dark');
		expect(get(theme)).toBe('dark');
	});

	it('initTheme leaves the attribute unset with no stored choice, so CSS follows the OS', () => {
		const { html } = stubBrowser({ osDark: true });
		initTheme();
		expect(html.dataset.theme).toBeUndefined();
		expect(get(theme)).toBe('dark');
	});

	it('initTheme ignores a stored value that is not a theme', () => {
		const { html } = stubBrowser({ stored: 'hotdog-stand' });
		initTheme();
		expect(html.dataset.theme).toBeUndefined();
		expect(get(theme)).toBe('light');
	});

	it('initTheme follows the OS while no theme is picked, and stops once one is', () => {
		const listeners: ((e: { matches: boolean }) => void)[] = [];
		const html: Html = { dataset: {} };
		vi.stubGlobal('document', { documentElement: html });
		vi.stubGlobal('localStorage', { getItem: () => null, setItem: () => {} });
		vi.stubGlobal('matchMedia', () => ({
			matches: false,
			addEventListener: (_: string, fn: (e: { matches: boolean }) => void) => listeners.push(fn),
			removeEventListener: () => {}
		}));
		initTheme();
		expect(get(theme)).toBe('light');
		listeners.forEach((fn) => fn({ matches: true }));
		expect(get(theme)).toBe('dark');
		setTheme('apt');
		listeners.forEach((fn) => fn({ matches: false }));
		expect(get(theme)).toBe('apt');
	});

	it('initTheme falls back to the OS when storage throws', () => {
		const { html } = stubBrowser({ storage: 'throws', osDark: true });
		expect(() => initTheme()).not.toThrow();
		expect(html.dataset.theme).toBeUndefined();
		expect(get(theme)).toBe('dark');
	});
});

describe('the pre-paint script in app.html', () => {
	// app.html applies the stored theme before the app loads, so it cannot
	// import THEMES and keeps its own list. This is where the two drift.
	const html = readFileSync(new URL('../app.html', import.meta.url), 'utf8');

	it('accepts exactly the themes the store offers', () => {
		const m = /\[([^\]]*)\]\.indexOf\(t\)/.exec(html);
		expect(m, 'allow-list not found in app.html').not.toBeNull();
		const listed = [...m![1].matchAll(/'([^']+)'/g)].map((x) => x[1]);
		expect(listed).toEqual([...THEMES]);
	});

	it('runs before the app, in the head', () => {
		const head = html.slice(0, html.indexOf('</head>'));
		expect(head).toContain("localStorage.getItem('theme')");
		expect(head.indexOf("localStorage.getItem('theme')")).toBeLessThan(head.indexOf('%sveltekit.head%'));
	});
});
