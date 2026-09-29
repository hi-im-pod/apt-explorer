import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { PUBLISH_POLICIES, SOURCE_LABELS, sourceLabel } from './labels';
import type { PublishPolicy, Sources } from './types';

// The sample data/ at the repository root, which the pipeline's own tests
// hold to SOURCES.md. Reading it here catches a source added to the data
// without a display name.
const sources: Sources = JSON.parse(
	readFileSync(new URL('../../../../data/sources.json', import.meta.url), 'utf8')
);

describe('source labels', () => {
	it('names every source in sources.json', () => {
		for (const s of sources) {
			expect(SOURCE_LABELS[s.name], s.name).toBeDefined();
		}
	});

	it('keeps the registered-trademark sign out of names, which headings reuse', () => {
		// MITRE asks for "MITRE ATT&CK" in headings, with the sign only at the
		// first mention in running text. Page copy adds it there.
		for (const label of Object.values(SOURCE_LABELS)) {
			expect(label.name).not.toContain('®');
			expect(label.short).not.toContain('®');
		}
	});

	it('falls back to the key for a source it does not know', () => {
		expect(sourceLabel('newsource')).toEqual({ name: 'newsource', short: 'newsource', role: '' });
		expect(sourceLabel('dfir').name).toBe('The DFIR Report');
	});

	it('explains every publish policy', () => {
		const all: PublishPolicy[] = ['full', 'derived-only', 'link-only', 'evidence-only'];
		expect(Object.keys(PUBLISH_POLICIES).sort()).toEqual([...all].sort());
		for (const p of all) expect(PUBLISH_POLICIES[p].length).toBeGreaterThan(40);
	});
});
