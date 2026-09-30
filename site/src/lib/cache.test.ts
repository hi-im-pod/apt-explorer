import { describe, expect, it } from 'vitest';
import { DATA_CACHE, pruneTargets, planFor, versioned, versionOf } from './cache';

const ORIGIN = 'https://example.github.io';
const BASE = '/apt-explorer';
const plan = (path: string, init: { method?: string; cache?: RequestCache } = {}) =>
	planFor({ url: `${ORIGIN}${path}`, method: init.method ?? 'GET', cache: init.cache ?? 'default' }, ORIGIN, BASE);

describe('versioned', () => {
	it('adds the build time as a query the server ignores and the browser keys on', () => {
		expect(versioned('/apt-explorer/data/reports/index.json', '2026-09-28T03:21:05Z')).toBe(
			'/apt-explorer/data/reports/index.json?v=2026-09-28T03%3A21%3A05Z'
		);
	});
	it('reads the version back out of a URL', () => {
		const url = new URL(`${ORIGIN}${versioned('/apt-explorer/data/x.json', '2026-09-28T03:21:05Z')}`);
		expect(versionOf(url)).toBe('2026-09-28T03:21:05Z');
		expect(versionOf(new URL(`${ORIGIN}/apt-explorer/data/x.json`))).toBeNull();
	});
});

describe('planFor', () => {
	it('keeps versioned data for good, because its URL changes with every build', () => {
		expect(plan('/apt-explorer/data/reports/index.json?v=A')).toBe('versioned-data');
		expect(plan('/apt-explorer/data/reports/2024.json?v=A')).toBe('versioned-data');
	});
	it('always asks the network first for the build time, so a new build is seen at once', () => {
		expect(plan('/apt-explorer/data/build.json')).toBe('network-first');
	});
	it('asks the network first for a page and falls back to the copy it has', () => {
		expect(plan('/apt-explorer/explore/')).toBe('network-first');
		expect(plan('/apt-explorer/data/actors/G0007.json')).toBe('network-first');
	});
	it('keeps hashed app files, whose names change with their content', () => {
		expect(plan('/apt-explorer/_app/immutable/chunks/abc123.js')).toBe('immutable');
	});
	it('does not touch a request the page made to bypass every cache', () => {
		// The page uses "reload" to replace a copy it found to be from the wrong build.
		expect(plan('/apt-explorer/data/reports/index.json?v=A', { cache: 'reload' })).toBe('network-first');
	});
	it('leaves alone anything that is not a same-site GET under the base path', () => {
		expect(plan('/apt-explorer/data/x.json?v=A', { method: 'POST' })).toBe('bypass');
		expect(plan('/other/data/x.json?v=A')).toBe('bypass');
		expect(planFor({ url: 'https://elsewhere.example/apt-explorer/data/x.json?v=A', method: 'GET', cache: 'default' }, ORIGIN, BASE)).toBe('bypass');
	});
	it('works with no base path', () => {
		expect(planFor({ url: `${ORIGIN}/data/x.json?v=A`, method: 'GET', cache: 'default' }, ORIGIN, '')).toBe('versioned-data');
	});
	it('does not take a path that only starts with the base for one under it', () => {
		expect(plan('/apt-explorer-old/data/x.json?v=A')).toBe('bypass');
	});
});

describe('pruneTargets', () => {
	it('lists every copy from another build, whichever file it is', () => {
		const stored = [
			`${ORIGIN}/apt-explorer/data/reports/index.json?v=OLD`,
			`${ORIGIN}/apt-explorer/data/reports/index.json?v=NEW`,
			`${ORIGIN}/apt-explorer/data/reports/2024.json?v=OLD`,
			`${ORIGIN}/apt-explorer/data/campaigns.json?v=NEW`
		];
		expect(pruneTargets(stored, `${ORIGIN}/apt-explorer/data/reports/index.json?v=NEW`)).toEqual([
			stored[0],
			stored[2]
		]);
	});
	it('lists nothing when every copy is from the same build', () => {
		const stored = [`${ORIGIN}/apt-explorer/data/campaigns.json?v=NEW`];
		expect(pruneTargets(stored, `${ORIGIN}/apt-explorer/data/reports/index.json?v=NEW`)).toEqual([]);
	});
});

describe('names', () => {
	it('has one cache for data that outlives an app version', () => {
		expect(DATA_CACHE).toBe('aptx-data');
	});
});
