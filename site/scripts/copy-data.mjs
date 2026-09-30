// Copies the published data/ tree into static/data so the site serves it
// under its own base path. Runs before every build and dev server start.
//
// Usage: node scripts/copy-data.mjs [src] [dest]
// Defaults are resolved from this file's location, not the working
// directory, so the script does the same thing wherever npm is run from.
import { cpSync, existsSync, rmSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
// APTX_DATA points a build at a data set other than the committed one, for
// example a fresh pipeline run that has not been committed yet. The tests use
// the same variable, so the site and its tests read the same files.
const src = resolve(process.argv[2] ?? process.env.APTX_DATA ?? join(here, '..', '..', 'data'));
const dest = resolve(process.argv[3] ?? join(here, '..', 'static', 'data'));

// build.json is written last by the pipeline and is what the data layer
// reads first, so its absence means there is no complete data set. Check
// before deleting anything: a failed copy must leave the previous copy in
// place rather than a site with no data at all.
if (!existsSync(join(src, 'build.json'))) {
	console.error(`copy-data: ${join(src, 'build.json')} not found; run the pipeline first.`);
	process.exit(1);
}

// Remove the old copy first, so a shard or actor that the new data no
// longer has cannot survive in the built site.
rmSync(dest, { recursive: true, force: true });
cpSync(src, dest, { recursive: true });
console.log(`copy-data: ${src} -> ${dest}`);
