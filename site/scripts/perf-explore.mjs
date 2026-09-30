// Measures the explore page the way a visitor on a phone would meet it.
//
// It serves a built site the way GitHub Pages does (compressed, ten-minute
// cache headers), loads /explore/ in Chromium under a network throttle, and
// reports bytes, time to the first table row, time until the filters work and
// how long a filter takes to paint. A second visit in the same browser
// profile shows what the cache saves.
//
// Usage (from site/):  node scripts/perf-explore.mjs <build dir> [--base /apt-explorer]
//                      [--port 4190] [--profile fast4g|slow4g|none] [--runs 3]
import { chromium } from '@playwright/test';
import { startPagesServer } from './pages-server.mjs';

const args = process.argv.slice(2);
const dir = args[0];
const opt = (name, fallback) => {
	const i = args.indexOf(`--${name}`);
	return i >= 0 ? args[i + 1] : fallback;
};
const base = opt('base', '/apt-explorer');
const port = Number(opt('port', '4190'));
const runs = Number(opt('runs', '3'));
const profileName = opt('profile', 'fast4g');
// A phone is several times slower than a laptop, so the CPU can be throttled too.
const cpu = Number(opt('cpu', '1'));
// Pages' own max-age is 600 s; 0 shows what a visit later than that costs.
const maxAge = Number(opt('maxage', '600'));

// Chrome DevTools' presets, in bytes per second and milliseconds.
const PROFILES = {
	fast4g: { downloadThroughput: (9 * 1024 * 1024) / 8, uploadThroughput: (1.5 * 1024 * 1024) / 8, latency: 60 },
	slow4g: { downloadThroughput: (1.6 * 1024 * 1024) / 8, uploadThroughput: (750 * 1024) / 8, latency: 150 },
	none: null
};

const median = (xs) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)];

/** Page-side probe: marks when the first row is painted and when the filters are usable. */
const PROBE = `
window.__probe = { row: null, ready: null, filter: null };
new MutationObserver(() => {
	const p = window.__probe;
	if (p.row == null && document.querySelector('[role="table"] [role="cell"]')) {
		requestAnimationFrame(() => { if (p.row == null) p.row = performance.now(); });
	}
	const s = document.querySelector('[role="status"]');
	if (p.ready == null && s && /showing/i.test(s.textContent || '')) {
		requestAnimationFrame(() => { if (p.ready == null) p.ready = performance.now(); });
	}
}).observe(document, { subtree: true, childList: true, characterData: true });
`;

async function visit(browser, server, context, label) {
	const page = context.pages()[0] ?? (await context.newPage());
	const cdp = await context.newCDPSession(page);
	await cdp.send('Network.enable');
	if (cpu > 1) await cdp.send('Emulation.setCPUThrottlingRate', { rate: cpu });
	const profile = PROFILES[profileName];
	if (profile) await cdp.send('Network.emulateNetworkConditions', { offline: false, ...profile });

	const kinds = new Map();
	const urls = new Map();
	cdp.on('Network.responseReceived', (e) => urls.set(e.requestId, { url: e.response.url, status: e.response.status, fromCache: e.response.fromDiskCache || e.response.fromServiceWorker }));
	const raw = new Map();
	cdp.on('Network.dataReceived', (e) => raw.set(e.requestId, (raw.get(e.requestId) ?? 0) + e.dataLength));
	cdp.on('Network.loadingFinished', (e) => {
		const u = urls.get(e.requestId);
		if (!u) return;
		const path = new URL(u.url).pathname.replace(base, '');
		const kind = /\/data\/reports\//.test(path) ? 'reports' : /\/data\//.test(path) ? 'other data' : 'app';
		const k = kinds.get(kind) ?? { wire: 0, raw: 0, requests: 0 };
		k.wire += e.encodedDataLength;
		k.raw += raw.get(e.requestId) ?? 0;
		k.requests += 1;
		kinds.set(kind, k);
	});
	await page.addInitScript(PROBE);
	const t0 = Date.now();
	await page.goto(`${server.url}${base}/explore/`, { waitUntil: 'commit' });
	await page.waitForFunction(() => window.__probe?.ready != null, null, { timeout: 120_000, polling: 50 });
	const wall = Date.now() - t0;
	const probe = await page.evaluate(() => window.__probe);
	const totals = Object.fromEntries([...kinds].map(([k, v]) => [k, v]));

	// A filter: pick the first source in the list and time the paint from the
	// moment the page changes the address, which is after any typing delay.
	const filterMs = await page.evaluate(async () => {
		const results = [];
		const status = document.querySelector('[role="status"]');
		const original = history.replaceState.bind(history);
		let t = 0;
		history.replaceState = (...a) => { t = performance.now(); return original(...a); };
		const settle = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
		async function step(act) {
			const before = status.textContent;
			t = 0;
			const done = new Promise((resolve) => {
				const obs = new MutationObserver(() => {
					if (status.textContent !== before && t) { obs.disconnect(); settle().then(() => resolve(performance.now() - t)); }
				});
				obs.observe(status, { subtree: true, childList: true, characterData: true });
				setTimeout(() => { obs.disconnect(); resolve(-1); }, 8000);
			});
			act();
			return done;
		}
		const setValue = (el, v) => {
			const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
			Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v);
		};
		const src = document.querySelector('#f-source');
		const opts = [...src.options].map((o) => o.value).filter(Boolean);
		results.push(['source', await step(() => { setValue(src, opts[0]); src.dispatchEvent(new Event('change', { bubbles: true })); })]);
		results.push(['clear source', await step(() => { setValue(src, ''); src.dispatchEvent(new Event('change', { bubbles: true })); })]);
		const q = document.querySelector('#f-q');
		results.push(['search "phishing"', await step(() => { setValue(q, 'phishing'); q.dispatchEvent(new Event('input', { bubbles: true })); })]);
		results.push(['search "apt29 loader"', await step(() => { setValue(q, 'apt29 loader'); q.dispatchEvent(new Event('input', { bubbles: true })); })]);
		results.push(['clear search', await step(() => { setValue(q, ''); q.dispatchEvent(new Event('input', { bubbles: true })); })]);
		history.replaceState = original;
		return results;
	});
	return { label, wall, rowMs: Math.round(probe.row), readyMs: Math.round(probe.ready), bytes: totals, filterMs };
}

const server = await startPagesServer({ dir, base, port, maxAge });
const cold = [];
const warm = [];
for (let i = 0; i < runs; i++) {
	const browser = await chromium.launch();
	const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
	cold.push(await visit(browser, server, context, 'cold'));
	await context.pages()[0].close();
	warm.push(await visit(browser, server, context, 'warm'));
	await browser.close();
}
await server.close();

const fmt = (b) => `${(b / 1024).toFixed(0)} KB`;
for (const [name, list] of [['cold', cold], ['warm', warm]]) {
	console.log(`\n== ${name} (${profileName}, median of ${runs}) ==`);
	console.log('first row ms', median(list.map((r) => r.rowMs)), '| filters ready ms', median(list.map((r) => r.readyMs)));
	const kinds = new Set(list.flatMap((r) => Object.keys(r.bytes)));
	for (const k of kinds) {
		const wire = median(list.map((r) => r.bytes[k]?.wire ?? 0));
		const n = median(list.map((r) => r.bytes[k]?.requests ?? 0));
		const rawB = median(list.map((r) => r.bytes[k]?.raw ?? 0));
		console.log(`  ${k}: ${fmt(wire)} gzip over the wire, ${fmt(rawB)} uncompressed, ${n} requests`);
	}
	const first = list[0].filterMs;
	for (let i = 0; i < first.length; i++) {
		console.log(`  filter "${first[i][0]}": ${median(list.map((r) => Math.round(r.filterMs[i][1])))} ms`);
	}
}
