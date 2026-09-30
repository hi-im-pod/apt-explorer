// A small static server that answers the way GitHub Pages does, for measuring
// and for tests that need real cache behaviour.
//
// `vite preview` sends no cache headers and no compression, so a network
// throttle against it counts bytes the real host would never send, and a
// warm visit against it never exercises the browser cache. Pages compresses
// text, sends `cache-control: max-age=600` and an ETag, and answers a
// conditional request with 304. This server does the same, and can replace a
// file's body at run time, which is how a test simulates a new data build.
//
// Usage: node scripts/pages-server.mjs <dir> <base> <port>
import { createReadStream, existsSync, readFileSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { extname, join, normalize, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

/** @type {Record<string, string>} */
const TYPES = {
	'.html': 'text/html; charset=utf-8',
	'.js': 'text/javascript; charset=utf-8',
	'.css': 'text/css; charset=utf-8',
	'.json': 'application/json; charset=utf-8',
	'.svg': 'image/svg+xml',
	'.txt': 'text/plain; charset=utf-8',
	'.md': 'text/markdown; charset=utf-8',
	'.woff2': 'font/woff2',
	'.woff': 'font/woff'
};
const COMPRESSIBLE = new Set(['.html', '.js', '.css', '.json', '.svg', '.txt', '.md']);

/**
 * @param {{ dir: string, base: string, port: number, maxAge?: number }} options
 * @returns {Promise<{ url: string, requests: string[], override: (path: string, body: string | null) => void, delay: (ms: number) => void, close: () => Promise<void> }>}
 */
export function startPagesServer({ dir, base, port, maxAge = 600 }) {
	const root = resolve(dir);
	/** Paths (below the base) whose body a test has replaced. */
	const overrides = new Map();
	/** Every request path with its query, in arrival order, so a test can count fetches. */
	/** @type {string[]} */
	const requests = [];
	const gzipCache = new Map();
	let extraDelay = 0;

	/** @param {string} rel */
	function fileFor(rel) {
		const clean = normalize(decodeURIComponent(rel)).replace(/^([/\\])+/, '');
		let file = join(root, clean);
		if (!file.startsWith(root + sep) && file !== root) return null;
		if (existsSync(file) && statSync(file).isDirectory()) file = join(file, 'index.html');
		return existsSync(file) ? file : null;
	}

	const server = createServer((req, res) => {
		const send = () => {
			const url = new URL(req.url ?? '/', 'http://x');
			requests.push(url.pathname + url.search);
			if (url.pathname === base) {
				res.writeHead(301, { location: `${base}/` }).end();
				return;
			}
			if (!url.pathname.startsWith(`${base}/`)) {
				res.writeHead(404).end('not found');
				return;
			}
			let rel = url.pathname.slice(base.length + 1);
			// Pages redirects a directory to its trailing-slash form.
			const asFile = fileFor(rel);
			if (rel && !rel.endsWith('/') && asFile && asFile.endsWith('index.html') && !extname(rel)) {
				res.writeHead(301, { location: `${base}/${rel}/` }).end();
				return;
			}
			let body;
			let type;
			let status = 200;
			let stamp;
			if (overrides.has(rel)) {
				body = Buffer.from(overrides.get(rel));
				type = TYPES[extname(rel)] ?? 'application/octet-stream';
				stamp = `o${body.length}-${overrides.get(rel).length}`;
			} else {
				let file = asFile;
				if (!file) {
					file = join(root, '404.html');
					status = 404;
				}
				const st = statSync(file);
				type = TYPES[extname(file)] ?? 'application/octet-stream';
				stamp = `${st.size.toString(16)}-${Math.floor(st.mtimeMs).toString(16)}`;
				body = file;
			}
			const ext = extname(typeof body === 'string' ? body : rel);
			const headers = {
				'content-type': type,
				'cache-control': `max-age=${maxAge}`,
				etag: `"${stamp}"`,
				'accept-ranges': 'bytes'
			};
			if (status === 200 && req.headers['if-none-match'] === headers.etag) {
				res.writeHead(304, headers).end();
				return;
			}
			const wantsGzip = COMPRESSIBLE.has(ext) && /\bgzip\b/.test(String(req.headers['accept-encoding']));
			if (wantsGzip) {
				const key = typeof body === 'string' ? `${body}|${stamp}` : `${rel}|${stamp}`;
				let gz = gzipCache.get(key);
				if (!gz) {
					gz = gzipSync(typeof body === 'string' ? readFileSync(body) : body);
					gzipCache.set(key, gz);
				}
				res.writeHead(status, { ...headers, 'content-encoding': 'gzip', vary: 'Accept-Encoding', 'content-length': gz.length });
				res.end(gz);
			} else if (typeof body === 'string') {
				res.writeHead(status, headers);
				createReadStream(body).pipe(res);
			} else {
				res.writeHead(status, { ...headers, 'content-length': body.length });
				res.end(body);
			}
		};
		if (extraDelay) setTimeout(send, extraDelay);
		else send();
	});

	return new Promise((ok, fail) => {
		server.once('error', fail);
		server.listen(port, '127.0.0.1', () => {
			ok({
				url: `http://127.0.0.1:${port}`,
				requests,
				override: (path, body) => (body == null ? overrides.delete(path) : overrides.set(path, body)),
				delay: (ms) => {
					extraDelay = ms;
				},
				close: () =>
					new Promise((done) => {
						server.closeAllConnections();
						server.close(() => done());
					})
			});
		});
	});
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
	const [dir, base, port] = process.argv.slice(2);
	const s = await startPagesServer({ dir, base, port: Number(port) });
	console.log(`serving ${dir} at ${s.url}${base}/`);
}
