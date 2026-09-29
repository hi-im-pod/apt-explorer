import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, describe, expect, it } from 'vitest';

const SCRIPT = fileURLToPath(new URL('./copy-data.mjs', import.meta.url));
let dirs: string[] = [];

function tmp(): string {
	const d = mkdtempSync(join(tmpdir(), 'aptx-copy-'));
	dirs.push(d);
	return d;
}

function run(src: string, dest: string) {
	return execFileSync(process.execPath, [SCRIPT, src, dest], { encoding: 'utf8', stdio: 'pipe' });
}

afterEach(() => {
	for (const d of dirs) rmSync(d, { recursive: true, force: true });
	dirs = [];
});

describe('copy-data', () => {
	it('copies the whole data tree, nested shards included', () => {
		const src = tmp();
		const dest = join(tmp(), 'static', 'data');
		mkdirSync(join(src, 'reports'), { recursive: true });
		writeFileSync(join(src, 'build.json'), '{"version":"t"}');
		writeFileSync(join(src, 'reports', '2024.json'), '[]');
		run(src, dest);
		expect(readFileSync(join(dest, 'build.json'), 'utf8')).toBe('{"version":"t"}');
		expect(readFileSync(join(dest, 'reports', '2024.json'), 'utf8')).toBe('[]');
	});

	it('removes files the new data no longer has', () => {
		// A shard or actor dropped from data/ must not live on in the built
		// site just because an old copy was still sitting in static/.
		const src = tmp();
		const dest = tmp();
		writeFileSync(join(src, 'build.json'), '{}');
		writeFileSync(join(dest, 'stale.json'), '{}');
		run(src, dest);
		expect(existsSync(join(dest, 'stale.json'))).toBe(false);
		expect(existsSync(join(dest, 'build.json'))).toBe(true);
	});

	it('fails, and leaves the old copy alone, when there is no published data', () => {
		const src = tmp();
		const dest = tmp();
		writeFileSync(join(dest, 'build.json'), '{"old":true}');
		expect(() => run(join(src, 'missing'), dest)).toThrow(/build\.json/);
		expect(readFileSync(join(dest, 'build.json'), 'utf8')).toBe('{"old":true}');
	});
});
