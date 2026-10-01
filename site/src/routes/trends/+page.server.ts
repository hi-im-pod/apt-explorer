import { getActorsIndex, getTrends, getVulns } from '$lib/data';
import type { PageServerLoad } from './$types';

/**
 * The trends, the display name of every actor they mention, and the EPSS score of
 * every CVE in the exploited-vulnerability table.
 *
 * This runs at build time only. A universal load would inline every
 * response it fetched, and the actors index grows with the registry, while
 * the page needs only a few dozen names, and the vulnerability list holds every
 * KEV and report CVE. A server load publishes just what it returns.
 */
export const load: PageServerLoad = async ({ fetch }) => {
	const [trends, actors, vulns] = await Promise.all([
		getTrends(fetch),
		getActorsIndex(fetch),
		getVulns(fetch)
	]);
	const mentioned = new Set<string>([
		...trends.reporting_activity.map((r) => r.actor),
		...trends.new_actors.map((r) => r.actor),
		...trends.kev_actor_links.flatMap((r) => r.actors),
		...trends.reported_vs_documented.map((r) => r.actor)
	]);
	const names: Record<string, string> = {};
	for (const a of actors) if (mentioned.has(a.id)) names[a.id] = a.name;
	const listed = new Set(trends.kev_actor_links.map((r) => r.cve));
	const scores: Record<string, number> = {};
	for (const v of vulns) if (listed.has(v.cve) && v.epss !== null) scores[v.cve] = v.epss;
	return { trends, names, scores };
};
