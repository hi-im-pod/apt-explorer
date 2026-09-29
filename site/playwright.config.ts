import { defineConfig, devices } from '@playwright/test';

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
		command: 'npm run build && npx vite preview --port 4173 --strictPort',
		port: 4173,
		env: { BASE_PATH: '/apt-explorer' },
		timeout: 240_000,
		reuseExistingServer: false
	},
	use: { baseURL: 'http://localhost:4173' },
	projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }]
});
