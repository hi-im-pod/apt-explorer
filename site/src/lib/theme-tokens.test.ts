import { readFileSync } from 'node:fs';
import { describe, it, expect } from 'vitest';

// These tests read the colour tokens out of app.css itself. A copy of the
// values in this file would only prove that the copy passes.
const CSS = readFileSync(new URL('../app.css', import.meta.url), 'utf8');

type Block = { selector: string; media: string | null; body: string };

/** Top-level and one-level-nested rule blocks, with comments removed. */
function blocks(css: string): Block[] {
	const src = css.replace(/\/\*[\s\S]*?\*\//g, '');
	const out: Block[] = [];
	const stack: { head: string; start: number }[] = [];
	let head = '';
	for (let i = 0; i < src.length; i++) {
		const ch = src[i];
		if (ch === '{') {
			stack.push({ head: head.trim(), start: i + 1 });
			head = '';
		} else if (ch === '}') {
			const open = stack.pop();
			if (!open) throw new Error(`Unbalanced } at ${i}`);
			const parent = stack.at(-1);
			if (!open.head.startsWith('@')) {
				out.push({
					selector: open.head,
					media: parent?.head.startsWith('@media') ? parent.head : null,
					body: src.slice(open.start, i)
				});
			}
			head = '';
		} else if (ch === ';' && stack.length === 0) {
			head = '';
		} else {
			head += ch;
		}
	}
	return out;
}

function tokens(body: string): Record<string, string> {
	const t: Record<string, string> = {};
	for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) t[m[1]] = m[2].trim();
	return t;
}

function block(selector: string, media: string | null = null): Record<string, string> {
	const found = blocks(CSS).filter((b) => b.selector === selector && b.media === media);
	if (found.length !== 1) {
		throw new Error(`Expected one "${selector}" block (media ${media}), found ${found.length}`);
	}
	return tokens(found[0].body);
}

const DARK_MEDIA = '@media (prefers-color-scheme: dark)';
const light = block(':root');
const darkExplicit = block(':root[data-theme="dark"]');
const darkSystem = block(':root:not([data-theme])', DARK_MEDIA);
const apt = block(':root[data-theme="apt"]');

const THEMES = {
	light,
	dark: { ...light, ...darkExplicit },
	apt: { ...light, ...apt }
} as const;

const COLOUR_TOKENS = [
	'--bg',
	'--surface',
	'--text',
	'--text-muted',
	'--accent',
	'--accent-2',
	'--border',
	'--danger',
	'--chart-1',
	'--chart-2',
	'--chart-3',
	'--chart-4',
	'--chart-5',
	'--chart-6'
];

function rgb(hex: string): [number, number, number] {
	const m = /^#([0-9a-f]{6})$/i.exec(hex);
	if (!m) throw new Error(`${hex} is not a #rrggbb colour`);
	const n = parseInt(m[1], 16);
	return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** WCAG 2.x relative luminance. */
function luminance(hex: string): number {
	const [r, g, b] = rgb(hex).map((c) => {
		const s = c / 255;
		return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
	});
	return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(a: string, b: string): number {
	const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
	return (hi + 0.05) / (lo + 0.05);
}

describe('contrast()', () => {
	it('matches the WCAG reference points', () => {
		expect(contrast('#000000', '#ffffff')).toBeCloseTo(21, 5);
		expect(contrast('#777777', '#777777')).toBe(1);
		// #767676 on white is the usual example of a grey that just passes AA.
		expect(contrast('#767676', '#ffffff')).toBeGreaterThanOrEqual(4.5);
		expect(contrast('#777777', '#ffffff')).toBeLessThan(4.5);
	});
});

describe('theme tokens', () => {
	it('keeps the system-dark tokens identical to the chosen-dark tokens', () => {
		// The dark palette is written twice, once for visitors whose OS is dark
		// and once for visitors who pick Dark. This is where the two drift.
		expect(darkSystem).toEqual(darkExplicit);
	});

	it.each(Object.entries({ light, dark: darkExplicit, apt }))(
		'%s sets every colour token itself, as #rrggbb',
		(_name, own) => {
			// A token a theme forgets falls through to the light value, which
			// is how light text ends up on a dark background.
			for (const t of COLOUR_TOKENS) {
				expect(own[t], t).toBeDefined();
				expect(() => rgb(own[t]), t).not.toThrow();
			}
		}
	);

	it('defines both font stacks', () => {
		for (const theme of Object.values(THEMES)) {
			expect(theme['--font-body']).toBeTruthy();
			expect(theme['--font-data']).toBeTruthy();
		}
	});

	it('keeps the APT theme values the spec pins', () => {
		expect(apt['--bg']).toBe('#07090a');
		expect(apt['--surface']).toBe('#0d1210');
		expect(apt['--text']).toBe('#c8f7c5');
		expect(apt['--accent']).toBe('#39ff88');
		expect(apt['--accent-2']).toBe('#ffb000');
		expect(apt['--font-body']).toMatch(/^ui-monospace\b/);
	});
});

describe.each(Object.entries(THEMES))('%s theme contrast (WCAG AA)', (_name, t) => {
	// Text, muted text and both accents are used as text, so they need 4.5:1
	// on both the page and the raised surface that tables and panels use.
	const textTokens = ['--text', '--text-muted', '--accent', '--accent-2', '--danger'];
	for (const fg of textTokens) {
		for (const bg of ['--bg', '--surface']) {
			it(`${fg} on ${bg} reaches 4.5:1`, () => {
				expect(contrast(t[fg], t[bg])).toBeGreaterThanOrEqual(4.5);
			});
		}
	}

	// Chart marks are graphics, so WCAG 1.4.11 asks 3:1 against what they sit on.
	for (let i = 1; i <= 6; i++) {
		for (const bg of ['--bg', '--surface']) {
			it(`--chart-${i} on ${bg} reaches 3:1`, () => {
				expect(contrast(t[`--chart-${i}`], t[bg])).toBeGreaterThanOrEqual(3);
			});
		}
	}
});
