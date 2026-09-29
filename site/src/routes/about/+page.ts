import { getSources } from '$lib/data';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch }) => ({ sources: await getSources(fetch) });
