import { defineConfig, devices } from '@playwright/test';

// Parallel worktrees each start their own preview server, so the port comes
// from PW_PORT when two test runs must not collide. The default stays 4173.
const port = Number(process.env.PW_PORT ?? 4173);

export default defineConfig({
	testDir: 'tests',
	reporter: 'list',
	// Each test loads a prerendered page from one preview server, so they are
	// independent and safe to run in parallel.
	fullyParallel: true,
	webServer: {
		// The tests run against the production build under the real base path,
		// because that is what Pages serves. A dev server would hide base-path
		// and prerender mistakes.
		command: `npm run build && npx vite preview --port ${port} --strictPort`,
		port,
		env: { BASE_PATH: '/apt-explorer' },
		timeout: 240_000,
		reuseExistingServer: false
	},
	use: {
		baseURL: `http://localhost:${port}`,
		// The site registers a service worker. Playwright's page.route cannot
		// see requests the worker answers, so the specs that change what the
		// server sends would see the worker's copy instead. They run without
		// the worker, and the one spec about the worker (explore-cache.spec.ts)
		// opens its own browser context with it allowed.
		serviceWorkers: 'block'
	},
	projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }]
});
