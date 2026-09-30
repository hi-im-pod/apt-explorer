/**
 * The stub pages for slugs that were merged into another actor.
 *
 * data/slugs.json keeps every slug ever published. When two tracked actors turn out to be one,
 * the older slug lives on and the newer one is retired with `merged_into`. Anyone who bookmarked
 * or linked the retired address should land somewhere useful, so it gets a small page that says
 * what happened and links to the actor that took over.
 */
import type { SlugEntry, SlugRegistry } from '$lib/data';

export interface RetiredStub {
	slug: string;
	display_name: string;
	successor: { slug: string; display_name: string };
}

/**
 * One stub per merged slug, keyed by slug and sorted by it.
 *
 * A retired slug with no `merged_into` (the actor left the data without being merged) gets no
 * stub, because there is no successor to point to and a page that only says "gone" adds nothing
 * over the site's own not-found page. A stub whose successor is missing or also retired is
 * skipped for the same reason; the pipeline's cross-check already resolves chains, so this only
 * guards a hand-edited file. The successor's name is the one its entry shows now.
 */
export function retiredStubs(registry: SlugRegistry): Map<string, RetiredStub> {
	const live = new Map<string, SlugEntry>();
	for (const e of registry.entries) if (!e.retired) live.set(e.slug, e);

	const stubs: RetiredStub[] = [];
	for (const e of registry.entries) {
		if (!e.retired || e.merged_into === null) continue;
		const successor = live.get(e.merged_into);
		if (!successor) continue;
		stubs.push({
			slug: e.slug,
			display_name: e.display_name,
			successor: { slug: successor.slug, display_name: successor.display_name }
		});
	}
	stubs.sort((a, b) => (a.slug < b.slug ? -1 : a.slug > b.slug ? 1 : 0));
	return new Map(stubs.map((s) => [s.slug, s]));
}
