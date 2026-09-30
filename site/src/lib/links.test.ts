import { describe, expect, it } from 'vitest';
import { classifyLink, describeLinks } from './links';

describe('classifyLink', () => {
	it('recognises the VX-Underground paper collection as a mirror', () => {
		const c = classifyLink(
			'https://papers.vx-underground.org/papers/Malware%20Defense/2023-05-17%20-%20x.pdf'
		);
		expect(c).toMatchObject({
			kind: 'vxug-mirror',
			label: 'Mirror on VX-Underground',
			copy: true,
			mirror: true,
			host: 'papers.vx-underground.org'
		});
		expect(c.explanation).toMatch(/not the publisher/i);
	});

	it('recognises ORKL archive copies', () => {
		const c = classifyLink('https://archive.orkl.eu/b677a3627fae4bbab0f1ff87deabeed64ed81699.pdf');
		expect(c).toMatchObject({ kind: 'orkl-archive', label: 'Archived copy on ORKL', copy: true, mirror: false });
	});

	it('recognises the CyberMonitor collection on GitHub, in either host and any case', () => {
		for (const href of [
			'https://github.com/CyberMonitor/APT_CyberCriminal_Campagin_Collections/raw/master/x.pdf',
			'https://github.com/cybermonitor/APT_CyberCriminal_Campagin_Collections/blob/master/x.pdf',
			'https://raw.githubusercontent.com/CyberMonitor/APT_CyberCriminal_Campagin_Collections/master/x.pdf'
		]) {
			expect(classifyLink(href), href).toMatchObject({
				kind: 'cybermonitor-mirror',
				label: 'CyberMonitor archive on GitHub',
				mirror: true
			});
		}
	});

	it('does not treat other GitHub repositories as a mirror', () => {
		expect(classifyLink('https://github.com/mandiant/apt1-report/blob/main/README.md')).toMatchObject({
			kind: 'publisher',
			copy: false
		});
		expect(classifyLink('https://github.com/CyberMonitorFake/x')).toMatchObject({ kind: 'publisher' });
	});

	it('recognises Box shared files as a mirror', () => {
		expect(classifyLink('https://app.box.com/s/ce4fr8p0mxv2pjcvh4pmma1q7oqc4vnc')).toMatchObject({
			kind: 'box-mirror',
			label: 'Mirror on Box',
			mirror: true
		});
	});

	it('recognises the Wayback Machine and archive.today', () => {
		expect(
			classifyLink('https://web.archive.org/web/20110406012907/http://www.symantec.com/x')
		).toMatchObject({ kind: 'wayback', label: 'Wayback Machine', copy: true, mirror: false });
		expect(classifyLink('https://archive.org/details/foo')).toMatchObject({ kind: 'wayback' });
		expect(classifyLink('https://archive.ph/AbCdE')).toMatchObject({ kind: 'archive-today' });
		expect(classifyLink('https://archive.today/AbCdE')).toMatchObject({ kind: 'archive-today' });
	});

	it('treats any other host as the original publisher, ignoring www and case', () => {
		const c = classifyLink('HTTPS://WWW.Example.COM/blog/report');
		expect(c).toMatchObject({
			kind: 'publisher',
			label: 'Original publisher',
			copy: false,
			mirror: false,
			host: 'example.com'
		});
	});

	it('does not match a lookalike host that only ends with a known name', () => {
		expect(classifyLink('https://notvx-underground.org/x.pdf').kind).toBe('publisher');
		expect(classifyLink('https://archive.orkl.eu.evil.example/x.pdf').kind).toBe('publisher');
	});

	it('returns an invalid class for malformed, empty and non-web addresses', () => {
		for (const href of ['', '   ', 'not a url', 'javascript:alert(1)', 'ftp://example.com/x', '//example.com']) {
			const c = classifyLink(href);
			expect(c.kind, href).toBe('invalid');
			expect(c.valid, href).toBe(false);
			expect(c.host).toBe('');
			expect(c.explanation.length).toBeGreaterThan(0);
		}
	});

	it('gives every class a label, a short label and an explanation', () => {
		for (const href of [
			'https://example.com/a',
			'https://papers.vx-underground.org/a.pdf',
			'https://archive.orkl.eu/a.pdf',
			'https://github.com/CyberMonitor/x',
			'https://app.box.com/s/a',
			'https://web.archive.org/web/1/http://a',
			'https://archive.ph/a',
			'nonsense'
		]) {
			const c = classifyLink(href);
			expect(c.label.length, href).toBeGreaterThan(0);
			expect(c.short.length, href).toBeGreaterThan(0);
			expect(c.explanation.length, href).toBeGreaterThan(20);
			expect(c.label + c.explanation).not.toContain('—');
		}
	});
});

const ORKL = 'https://archive.orkl.eu/aa.pdf';
const VX = 'https://papers.vx-underground.org/papers/x.pdf';
const PUB = 'https://vendor.example/report';

describe('describeLinks', () => {
	it('lists the original first, then the copy, when both exist', () => {
		const d = describeLinks({ url: PUB, url_ok: true, archive_url: ORKL });
		expect(d.situation).toBe('both');
		expect(d.links.map((l) => [l.role, l.class.kind])).toEqual([
			['original', 'publisher'],
			['copy', 'orkl-archive']
		]);
		expect(d.note).toMatch(/original publisher/i);
		expect(d.note).toMatch(/copy/i);
	});

	it('lists the copy first and flags the original when the last check failed', () => {
		const d = describeLinks({ url: PUB, url_ok: false, archive_url: ORKL });
		expect(d.links.map((l) => l.role)).toEqual(['copy', 'original']);
		expect(d.links[1].unreachable).toBe(true);
		expect(d.links[0].unreachable).toBe(false);
		expect(d.note).toMatch(/unreachable/i);
		expect(d.note).toMatch(/copy is listed first/i);
	});

	it('keeps an unreachable original when there is no copy, and says so', () => {
		const d = describeLinks({ url: PUB, url_ok: false, archive_url: null });
		expect(d.situation).toBe('original-only');
		expect(d.links).toHaveLength(1);
		expect(d.links[0].unreachable).toBe(true);
		expect(d.note).toMatch(/unreachable/i);
		expect(d.note).not.toMatch(/listed first/i);
	});

	it('reports an original with no copy', () => {
		const d = describeLinks({ url: PUB, url_ok: null, archive_url: null });
		expect(d.situation).toBe('original-only');
		expect(d.note).toMatch(/no copy/i);
	});

	it('says a lone mirror is a mirror and never presents it as the original', () => {
		const d = describeLinks({ url: VX, url_ok: null, archive_url: null });
		expect(d.situation).toBe('copies-only');
		expect(d.links).toHaveLength(1);
		expect(d.links[0].role).toBe('copy');
		expect(d.note).toBe('No original publisher link is known; this is a mirror.');
	});

	it('treats a mirror in the url slot plus the ORKL copy as two copies and no original', () => {
		const d = describeLinks({ url: VX, url_ok: null, archive_url: ORKL });
		expect(d.situation).toBe('copies-only');
		expect(d.links.map((l) => l.role)).toEqual(['copy', 'copy']);
		expect(d.links.map((l) => l.class.kind)).toEqual(['vxug-mirror', 'orkl-archive']);
		expect(d.note).toMatch(/^No original publisher link is known;/);
		expect(d.note).toMatch(/copies/);
	});

	it('says a lone archived copy is an archived copy, not a mirror', () => {
		const d = describeLinks({ url: null, url_ok: null, archive_url: ORKL });
		expect(d.situation).toBe('copies-only');
		expect(d.note).toBe('No original publisher link is known; this is an archived copy.');
	});

	it('treats a Wayback snapshot in the url slot as a copy', () => {
		const d = describeLinks({
			url: 'https://web.archive.org/web/2011/http://old.example/x',
			url_ok: null,
			archive_url: ORKL
		});
		expect(d.situation).toBe('copies-only');
		expect(d.links[0].class.kind).toBe('wayback');
	});

	it('flags an unreachable mirror as a mirror, not as a failed original', () => {
		const d = describeLinks({ url: VX, url_ok: false, archive_url: ORKL });
		expect(d.links.find((l) => l.class.kind === 'vxug-mirror')?.unreachable).toBe(true);
		expect(d.links.find((l) => l.class.kind === 'orkl-archive')?.unreachable).toBe(false);
		// The failed link is kept, behind the one that may still work.
		expect(d.links.map((l) => l.class.kind)).toEqual(['orkl-archive', 'vxug-mirror']);
		expect(d.note).toMatch(/^No original publisher link is known;/);
		expect(d.note).not.toMatch(/original link was unreachable/i);
	});

	it('reports no links at all', () => {
		const d = describeLinks({ url: null, url_ok: null, archive_url: null });
		expect(d.situation).toBe('none');
		expect(d.links).toEqual([]);
		expect(d.note).toBe('No link is recorded for this report.');
	});

	it('drops a malformed address rather than linking it', () => {
		const d = describeLinks({ url: 'not a url', url_ok: null, archive_url: ORKL });
		expect(d.links).toHaveLength(1);
		expect(d.links[0].class.kind).toBe('orkl-archive');
		expect(d.situation).toBe('copies-only');
	});

	it('never puts a mirror in the original role, for every mirror host', () => {
		for (const href of [
			VX,
			'https://github.com/CyberMonitor/x/raw/master/a.pdf',
			'https://app.box.com/s/abc'
		]) {
			const d = describeLinks({ url: href, url_ok: null, archive_url: ORKL });
			expect(d.links.filter((l) => l.role === 'original'), href).toEqual([]);
		}
	});
});
