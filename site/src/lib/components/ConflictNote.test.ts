import { describe, it, expect, vi } from 'vitest';
vi.mock('$app/paths', () => ({ base: '/apt-explorer' }));
import { render } from 'svelte/server';
import ConflictNote from './ConflictNote.svelte';
import SourceBadge from './SourceBadge.svelte';

/** Visible text with tags removed and whitespace collapsed. */
const text = (html: string) =>
	html
		.replace(/<!--[\s\S]*?-->/g, '')
		.replace(/<[^>]+>/g, '')
		.replace(/&amp;/g, '&')
		.replace(/\s+/g, ' ')
		.trim();

describe('SourceBadge', () => {
	it("shows the source's short name and links to its licence entry on About", () => {
		const { body } = render(SourceBadge, { props: { source: 'attack' } });
		expect(text(body)).toBe('ATT&CK');
		expect(body).toContain('href="/apt-explorer/about/#source-attack"');
		expect(body).toContain('title="MITRE ATT&amp;CK"');
	});

	it('renders without a link where a link would repeat on every row', () => {
		const { body } = render(SourceBadge, { props: { source: 'misp', link: false } });
		expect(body).not.toContain('<a');
		expect(text(body)).toBe('MISP');
	});

	it('falls back to the key for a source the site has no label for', () => {
		const { body } = render(SourceBadge, { props: { source: 'newsource' } });
		expect(text(body)).toBe('newsource');
	});
});

describe('ConflictNote', () => {
	it('names every source and the value each gives', () => {
		const { body } = render(ConflictNote, {
			props: {
				conflict: {
					field: 'origin',
					values: [
						{ value: 'US', source: 'misp', name: 'Alpha' },
						{ value: 'GB', source: 'malpedia', name: 'Alpha' }
					]
				}
			}
		});
		const t = text(body);
		expect(t).toContain('The sources disagree on origin');
		expect(t).toContain('MISP gives US');
		expect(t).toContain('Malpedia gives GB');
		expect(body).toContain('role="note"');
	});

	it('uses the display function it is given, and groups sources that agree', () => {
		const names: Record<string, string> = { US: 'United States', GB: 'United Kingdom' };
		const { body } = render(ConflictNote, {
			props: {
				conflict: {
					field: 'origin',
					values: [
						{ value: 'US', source: 'misp', name: 'Alpha' },
						{ value: 'US', source: 'etda', name: 'Alpha' },
						{ value: 'GB', source: 'malpedia', name: 'Alpha' }
					]
				},
				display: (v: string) => names[v] ?? v
			}
		});
		const t = text(body);
		expect(t).toContain('MISP and ETDA give United States');
		expect(t).toContain('Malpedia gives United Kingdom');
	});

	it('names the records behind each value, and leaves out the actor own name', () => {
		const { body } = render(ConflictNote, {
			props: {
				conflict: {
					field: 'origin',
					values: [
						{ value: 'IR', source: 'misp', name: 'IRIDIUM' },
						{ value: 'IR', source: 'etda', name: 'Seashell Blizzard' },
						{ value: 'RU', source: 'misp', name: 'Sandworm Team' },
						{ value: 'RU', source: 'etda', name: 'Energetic Bear' },
						{ value: 'RU', source: 'etda', name: 'TeleBots' },
						{ value: 'RU', source: 'etda', name: 'Voodoo Bear' },
						{ value: 'RU', source: 'etda', name: 'BlackEnergy' }
					]
				},
				actorName: 'Sandworm Team'
			}
		});
		const t = text(body);
		expect(t).toContain('MISP and ETDA give IR (IRIDIUM and Seashell Blizzard)');
		expect(t).toContain('MISP and ETDA give RU (Sandworm Team, Energetic Bear, TeleBots and 2 more)');
	});

	it('shows no names when the only record is the actor itself', () => {
		const { body } = render(ConflictNote, {
			props: {
				conflict: {
					field: 'origin',
					values: [
						{ value: 'US', source: 'misp', name: 'apt28' },
						{ value: 'GB', source: 'etda', name: 'Fancy Bear' }
					]
				},
				actorName: 'APT28'
			}
		});
		const t = text(body);
		expect(t).toContain('MISP gives US;');
		expect(t).toContain('ETDA gives GB (Fancy Bear)');
	});
});
