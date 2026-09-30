import { describe, expect, it } from 'vitest';
import { indexForm, shortId } from './report-id';

const SHA = 'ab12cd34ef56ab12cd34ef56ab12cd34ef56ab12';

describe('shortId', () => {
	it('cuts a digest to the index length', () => {
		expect(shortId(SHA, 8)).toBe('ab12cd34');
		expect(shortId(SHA, 10)).toBe('ab12cd34ef');
	});
	it('keeps an id that is not a digest whole', () => {
		expect(shortId('paper:2025-ccs-apt', 8)).toBe('paper:2025-ccs-apt');
	});
});

describe('indexForm', () => {
	it('turns a full id from an actor page link into the form the index holds', () => {
		expect(indexForm(SHA, 8)).toBe('ab12cd34');
	});
	it('leaves a short id alone', () => {
		expect(indexForm('ab12cd34', 8)).toBe('ab12cd34');
	});
	it('cuts a longer prefix from a link saved under another build', () => {
		expect(indexForm('ab12cd34ef', 8)).toBe('ab12cd34');
	});
	it('leaves a prefix shorter than the index length, and an id that is not a digest', () => {
		expect(indexForm('ab12cd', 8)).toBe('ab12cd');
		expect(indexForm('paper:2025-ccs', 8)).toBe('paper:2025-ccs');
	});
});
