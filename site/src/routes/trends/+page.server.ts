import { getActorsIndex, getTrends } from '$lib/data';
import type { PageServerLoad } from './$types';

/**
 * The trends and the display name of every actor they mention.
 *
 * This runs at build time only. A universal load would inline every
 * response it fetched, and the actors index grows with the registry, while
 * the page needs only a few dozen names. A server load publishes just what
 * it returns.
 */
export const load: PageServerLoad = async ({ fetch }) => {
	const [trends, actors] = await Promise.all([getTrends(fetch), getActorsIndex(fetch)]);
	const mentioned = new Set<string>([
		...trends.reporting_activity.map((r) => r.actor),
		...trends.new_actors.map((r) => r.actor),
		...trends.kev_actor_links.flatMap((r) => r.actors),
		...trends.reported_vs_documented.map((r) => r.actor)
	]);
	const names: Record<string, string> = {};
	for (const a of actors) if (mentioned.has(a.id)) names[a.id] = a.name;
	return { trends, names };
};
