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
	use: { baseURL: `http://localhost:${port}` },
	projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }]
});
