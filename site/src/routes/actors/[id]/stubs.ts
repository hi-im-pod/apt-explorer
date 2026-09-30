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
	/** The actor that took over, or null when this one left the data without being merged. */
	successor: { slug: string; display_name: string } | null;
}

/**
 * One stub per merged slug, keyed by slug and sorted by it.
 *
 * Every retired slug gets a page, because a published address must not turn into a not-found
 * page. One with no `merged_into` (the actor left the data without being merged) has no
 * successor to point to, and its stub says the actor is no longer listed. The same holds when
 * the successor is missing or also retired; the pipeline's cross-check already resolves chains,
 * so that only guards a hand-edited file. The successor's name is the one its entry shows now.
 */
export function retiredStubs(registry: SlugRegistry): Map<string, RetiredStub> {
	const live = new Map<string, SlugEntry>();
	for (const e of registry.entries) if (!e.retired) live.set(e.slug, e);

	const stubs: RetiredStub[] = [];
	for (const e of registry.entries) {
		if (!e.retired) continue;
		const successor = e.merged_into === null ? undefined : live.get(e.merged_into);
		stubs.push({
			slug: e.slug,
			display_name: e.display_name,
			successor: successor ? { slug: successor.slug, display_name: successor.display_name } : null
		});
	}
	stubs.sort((a, b) => (a.slug < b.slug ? -1 : a.slug > b.slug ? 1 : 0));
	return new Map(stubs.map((s) => [s.slug, s]));
}
