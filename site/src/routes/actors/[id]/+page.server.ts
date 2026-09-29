/**
 * Loads one actor profile at build time.
 *
 * This is a server load, not a universal one, because of what prerender
 * writes into each page. A universal load's fetched files are inlined into
 * the HTML so the browser need not fetch them again; a profile needs the
 * report shards to turn report IDs into titles, so every profile would carry
 * every shard it touched, megabytes each once the real reports arrive, times
 * a thousand actors. A server load's fetches stay on the build machine, and
 * only its return value (this actor's own reports) is written into the page
 * and its __data.json. The data layer is still the only way in, so a later
 * server deployment changes nothing here.
 */
import { error } from '@sveltejs/kit';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { DataError, getActor, getReports, type Actor, type ActorsIndex, type Report } from '$lib/data';
import { pickReports } from './profile';
import type { EntryGenerator, PageServerLoad } from './$types';

/**
 * Every published actor ID, so each profile is prerendered even if no page
 * links to it. npm runs the build from site/, after the prebuild script has
 * copied data/ into static/data, so this reads the same index the site
 * serves.
 */
export const entries: EntryGenerator = () => {
	const index = JSON.parse(readFileSync(resolve('static/data/actors/index.json'), 'utf8')) as ActorsIndex;
	return index.map((a) => ({ id: a.id }));
};

// Prerender runs every profile in one process, and each needs the same
// shards. Reading and parsing them once instead of once per actor keeps the
// build linear in the number of reports rather than actors times reports.
// A failed read is not cached, so the next request tries again.
let reportsById: Promise<Map<string, Report>> | undefined;

function loadReports(fetch: typeof globalThis.fetch): Promise<Map<string, Report>> {
	reportsById ??= getReports(fetch, 'all').then(
		(all) => new Map(all.map((r) => [r.id, r])),
		(e: unknown) => {
			reportsById = undefined;
			throw e;
		}
	);
	return reportsById;
}

export const load: PageServerLoad = async ({ fetch, params }) => {
	let actor: Actor;
	try {
		actor = await getActor(fetch, params.id);
	} catch (e) {
		// A missing actor file is a missing page: the site's own not-found
		// page, not a failed build or an unstyled error.
		if (e instanceof DataError) error(e.status === 404 ? 404 : 500, e.status === 404 ? 'Not found' : e.message);
		throw e;
	}
	if (actor.reports.length === 0) return { actor, reports: [] };

	const { reports, missing } = pickReports(actor.reports, await loadReports(fetch));
	if (missing.length > 0) {
		// The pipeline's contract says every listed report is in a shard. If
		// one is not, the profile shows the rest, and the build log names the
		// gap rather than hiding it.
		console.warn(`actors/${actor.id}: ${missing.length} report IDs are in no shard: ${missing.slice(0, 5).join(', ')}`);
	}
	return { actor, reports };
};
