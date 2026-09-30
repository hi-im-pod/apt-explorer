import { describe, expect, it } from 'vitest';
import type { SlugEntry } from '$lib/data';
import { retiredStubs } from './stubs';

function entry(over: Partial<SlugEntry> & { slug: string }): SlugEntry {
	return {
		display_name: over.slug,
		anchors: [`misp:${over.slug}`],
		first_published: '2026-09-01',
		suffix: null,
		retired: false,
		merged_into: null,
		...over
	};
}

describe('retiredStubs', () => {
	it('makes one stub for each merged slug, naming the actor it went into', () => {
		const stubs = retiredStubs({
			entries: [
				entry({ slug: 'glass-heron', display_name: 'Glass Heron' }),
				entry({ slug: 'old-heron', display_name: 'Old Heron', retired: true, merged_into: 'glass-heron' })
			]
		});
		expect([...stubs.keys()]).toEqual(['old-heron']);
		expect(stubs.get('old-heron')).toEqual({
			slug: 'old-heron',
			display_name: 'Old Heron',
			successor: { slug: 'glass-heron', display_name: 'Glass Heron' }
		});
	});

	it('uses the name the successor shows now, not the name the retired entry recorded for it', () => {
		const stubs = retiredStubs({
			entries: [
				entry({ slug: 'G0007', display_name: 'APT28' }),
				entry({ slug: 'fancy', display_name: 'Fancy', retired: true, merged_into: 'G0007' })
			]
		});
		expect(stubs.get('fancy')?.successor).toEqual({ slug: 'G0007', display_name: 'APT28' });
	});

	it('makes a stub with no successor for a slug that vanished without a merge, so the address does not die', () => {
		const stubs = retiredStubs({ entries: [entry({ slug: 'gone', display_name: 'Gone', retired: true })] });
		expect(stubs.get('gone')).toEqual({ slug: 'gone', display_name: 'Gone', successor: null });
	});

	it('makes a stub with no successor when the successor is missing or itself retired', () => {
		const stubs = retiredStubs({
			entries: [
				entry({ slug: 'a', retired: true, merged_into: 'b' }),
				entry({ slug: 'b', retired: true, merged_into: 'nowhere' })
			]
		});
		expect([...stubs.values()].map((s) => [s.slug, s.successor])).toEqual([
			['a', null],
			['b', null]
		]);
	});

	it('never turns a live actor into a stub', () => {
		const stubs = retiredStubs({ entries: [entry({ slug: 'live', merged_into: 'other' }), entry({ slug: 'other' })] });
		expect(stubs.size).toBe(0);
	});

	it('is sorted by slug so the prerendered pages come out in a stable order', () => {
		const stubs = retiredStubs({
			entries: [
				entry({ slug: 'z-old', retired: true, merged_into: 'main' }),
				entry({ slug: 'a-old', retired: true, merged_into: 'main' }),
				entry({ slug: 'main' })
			]
		});
		expect([...stubs.keys()]).toEqual(['a-old', 'z-old']);
	});
});
