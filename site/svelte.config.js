import adapter from '@sveltejs/adapter-static';

// GitHub Pages serves a project site under /<repo>/, and the site may later
// move to a server under some other prefix, so the base path always comes
// from the environment and nothing assumes a root deploy.
const base = process.env.BASE_PATH ?? '';

/** @type {import('@sveltejs/kit').Config} */
export default {
	compilerOptions: {
		// Runes mode for our own components only; libraries in node_modules
		// keep whatever mode they were written in.
		runes: ({ filename }) => (filename.split(/[/\\]/).includes('node_modules') ? undefined : true)
	},
	kit: {
		// Pages returns 404.html for any path it has no file for. Building the
		// fallback page means that miss renders the site's own styled
		// not-found page instead of GitHub's.
		adapter: adapter({ fallback: '404.html' }),
		paths: { base },
		// 'fail' turns a broken internal link into a failed build, so a dead
		// link never reaches the deployed site.
		prerender: { handleHttpError: 'fail', entries: ['*'] }
	}
};
