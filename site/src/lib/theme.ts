/**
 * The visitor's colour theme.
 *
 * The theme is applied as data-theme on <html>, which switches the token
 * block in app.css. With no stored choice the attribute stays unset, so CSS
 * follows the OS through prefers-color-scheme and this store only mirrors
 * what the OS picked. localStorage can be missing or throw (private
 * windows, blocked site data), so every access is wrapped and the site
 * works without it.
 *
 * Nothing here touches the DOM at import time: this module is also loaded
 * during prerender, where there is no document.
 */
import { writable } from 'svelte/store';

export const THEMES = ['light', 'dark', 'apt'] as const;
export type Theme = (typeof THEMES)[number];

/** The theme in effect: the stored choice, or the OS preference without one. */
export const theme = writable<Theme>('light');

const KEY = 'theme';
const DARK_QUERY = '(prefers-color-scheme: dark)';

export function isTheme(value: unknown): value is Theme {
	return (THEMES as readonly unknown[]).includes(value);
}

function readStored(): Theme | null {
	try {
		const value = localStorage.getItem(KEY);
		return isTheme(value) ? value : null;
	} catch {
		return null;
	}
}

function osTheme(): Theme {
	try {
		return matchMedia(DARK_QUERY).matches ? 'dark' : 'light';
	} catch {
		return 'light';
	}
}

/**
 * Sync the store and <html> with the stored choice, or with the OS when
 * there is none. Call once in the browser. The pre-paint script in app.html
 * has already set the attribute; this also drops an attribute holding a
 * value that is not a theme. Returns a function that stops following OS
 * changes.
 */
export function initTheme(): () => void {
	const stored = readStored();
	const root = document.documentElement;
	if (stored) {
		root.dataset.theme = stored;
		theme.set(stored);
		return () => {};
	}
	delete root.dataset.theme;
	theme.set(osTheme());

	// Keep the switcher's checked item right when the OS flips between light
	// and dark while the page is open.
	let query: MediaQueryList;
	try {
		query = matchMedia(DARK_QUERY);
	} catch {
		return () => {};
	}
	// An attribute means the visitor has picked a theme since, even if storage
	// refused to keep it, and a pick outranks the OS.
	const follow = (e: MediaQueryListEvent) => {
		if (!root.dataset.theme) theme.set(e.matches ? 'dark' : 'light');
	};
	query.addEventListener('change', follow);
	return () => query.removeEventListener('change', follow);
}

/** Apply a theme now and remember it when storage allows. */
export function setTheme(t: Theme): void {
	document.documentElement.dataset.theme = t;
	theme.set(t);
	try {
		localStorage.setItem(KEY, t);
	} catch {
		// Storage is blocked. The theme still applies for this page view.
	}
}
