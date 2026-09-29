/// <reference types="vitest/config" />
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// Kit options live in svelte.config.js only, so the adapter, base path and
// prerender rules are defined in one place.
export default defineConfig({
	plugins: [sveltekit()],
	test: {
		// Playwright specs live in tests/ and must not be collected by vitest.
		include: ['src/**/*.test.ts', 'scripts/**/*.test.ts']
	}
});
