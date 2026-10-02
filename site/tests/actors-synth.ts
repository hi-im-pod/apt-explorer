/**
 * Synthesized volume for the actors tests and screenshots.
 *
 * The sample data/ has 14 actors and at most 14 reports per actor; the real
 * data will have over a thousand actors and some with hundreds of reports.
 * These helpers answer the data requests of a client-side navigation with
 * synthesized files instead, so layout is tested at volume without changing
 * data/. Every test that uses them asserts an exact synthesized count, so a
 * navigation that silently fell back to the sample would fail.
 */
import { readFileSync } from 'node:fs';
import { expect, type Page, type Route } from '@playwright/test';
import * as devalue from 'devalue';
import type { Actor, ActorsIndex, ActorsIndexEntry, Report } from '../src/lib/data/types';

// Any prerendered profile with reports supplies the __data.json envelope.
const TEMPLATE = (
	JSON.parse(readFileSync(new URL('../../data/actors/index.json', import.meta.url), 'utf8')) as ActorsIndex
).find((a) => a.report_count > 0)!.id;

export const SYNTH_ACTORS = 120;
export const SYNTH_REPORTS = 300;
export const LONG = 'Umbrella-Cluster-Name-With-No-Spaces-That-A-Source-Uses-As-One-Alias-For-Tracking-Purposes-Only';

export function synthIndex(): ActorsIndex {
	const out: ActorsIndexEntry[] = [];
	for (let i = 1; i <= SYNTH_ACTORS - 1; i++) {
		const n = String(i).padStart(3, '0');
		out.push({
			id: `synth-${n}`,
			name: `Synthetic Actor ${n}`,
			aliases: [`Synthetic Actor ${n}`, `Cluster ${n}`, `${LONG}-${n}`],
			origin: i % 3 === 0 ? ['CN', 'RU'] : [],
			report_count: i,
			last_reported: i % 4 === 0 ? null : `2026-0${1 + (i % 9)}-1${i % 10}`,
			sources: ['attack', 'misp']
		});
	}
	out.push({
		id: 'synth-busy',
		name: 'Busy Synthetic Actor',
		aliases: ['Busy Synthetic Actor', 'Quiet Otter', LONG],
		origin: ['KP'],
		report_count: SYNTH_REPORTS,
		last_reported: '2026-09-20',
		sources: ['attack', 'misp', 'malpedia']
	});
	return out;
}

export function synthReports(): Report[] {
	const out: Report[] = [];
	for (let i = 0; i < SYNTH_REPORTS; i++) {
		// Newest first, as actor files list them; the last ten are undated.
		const dated = i < SYNTH_REPORTS - 10;
		const year = 2026 - Math.floor(i / 25);
		const month = String(12 - (i % 12)).padStart(2, '0');
		out.push({
			id: `synth-report-${i}`,
			title:
				i % 50 === 0
					? `A-report-title-that-is-one-unbroken-string-of-well-over-sixty-characters-${i}`
					: `Synthetic report ${i} on a long-running intrusion set and its tooling`,
			published: dated ? `${year}-${month}-15` : null,
			date_basis: dated ? 'malpedia-library' : 'unknown',
			organisation: i % 7 === 0 ? null : `Research Organisation Number ${i % 13}`,
			url: i % 11 === 0 ? null : `https://example.org/synthetic/${i}/`,
			url_ok: i % 5 === 0 ? false : true,
			archive_url: `https://example.org/archive/${i}.pdf`,
			actors: ['synth-busy'],
			actors_from_title: [],
			actors_from_text: [],
			actor_names_unresolved: [],
			cves: [],
			techniques: [],
			sources: ['orkl']
		});
	}
	return out;
}

export function synthActor(reports: Report[]): Actor {
	const timeline = new Map<string, number>();
	for (const r of reports) {
		if (!r.published) continue;
		const q = `${r.published.slice(0, 4)}-Q${Math.ceil(Number(r.published.slice(5, 7)) / 3)}`;
		timeline.set(q, (timeline.get(q) ?? 0) + 1);
	}
	const many = <T,>(n: number, f: (i: number) => T): T[] => Array.from({ length: n }, (_, i) => f(i));
	return {
		id: 'synth-busy',
		name: 'Busy Synthetic Actor',
		aliases: [
			{ value: 'Busy Synthetic Actor', sources: ['attack', 'misp'] },
			{ value: LONG, sources: ['misp'] },
			{ value: `${LONG}-${LONG}`, sources: ['malpedia', 'etda'] },
			...many(37, (i) => ({ value: `Alias Number ${i}`, sources: ['misp', 'malpedia'] }))
		],
		origin: [
			{ value: 'KP', source: 'misp' },
			{ value: 'CN', source: 'malpedia' },
			{ value: 'RU', source: 'etda' }
		],
		sponsor: [{ value: 'A state agency with a very long descriptive name', source: 'misp' }],
		motivation: [{ value: 'Espionage', source: 'misp' }],
		claimed_targets: {
			countries: many(30, (i) => ({ value: i < 5 ? ['US', 'KR', 'JP', 'GB', 'DE'][i] : `Country-name-without-spaces-${i}`, source: 'misp' })),
			sectors: many(20, (i) => ({ value: `Sector with a long name ${i}`, source: 'misp' }))
		},
		malware: many(25, (i) => ({ name: `MalwareFamily${i}`, source: i % 2 ? 'attack' : 'malpedia' })),
		techniques_documented: many(150, (i) => `T${1000 + i}${i % 3 === 0 ? '.001' : ''}`),
		techniques_reported: many(60, (i) => ({ id: `T${1100 + i}`, count: 60 - i })),
		cves: many(40, (i) => ({ cve: `CVE-2024-${10000 + i}`, kev: i % 2 === 0, ransomware: i % 2 === 0 ? i % 4 === 0 : null })),
		timeline: [...timeline].map(([quarter, count]) => ({ quarter, count })).sort((a, b) => (a.quarter < b.quarter ? -1 : 1)),
		reports: reports.map((r) => r.id),
		conflicts: [
			{
				field: 'origin',
				values: [
					{ value: 'KP', source: 'misp' },
					{ value: 'CN', source: 'malpedia' },
					{ value: 'RU', source: 'etda' }
				]
			}
		],
		evidence_count: 212,
		cluster_only: false
	};
}

/**
 * Answer a profile's __data.json with the synthesized actor.
 *
 * The envelope comes from the real prerendered file for a sample actor and
 * only the page's data is swapped, so the test does not depend on how
 * SvelteKit lays the file out beyond "one node per layout and page, with
 * devalue-encoded data". If that changes, this throws rather than passing.
 */
export async function serveSynthProfile(route: Route) {
	const real = await route.fetch({ url: route.request().url().replace('/synth-busy/', `/${TEMPLATE}/`) });
	const [first, ...rest] = (await real.text()).split('\n');
	const envelope = JSON.parse(first) as { type: string; nodes: ({ type: string; data: unknown } | null)[] };
	const node = envelope.nodes.at(-1);
	if (envelope.type !== 'data' || !node || node.type !== 'data') throw new Error(`Unexpected __data.json: ${first.slice(0, 200)}`);
	const data = devalue.unflatten(node.data as unknown[]) as { actor: Actor; reports: unknown[] };
	if (!data.actor || !Array.isArray(data.reports)) throw new Error('The page data no longer holds actor and reports');
	const reports = synthReports();
	data.actor = synthActor(reports);
	data.reports = reports.map(({ id, title, published, date_basis, organisation, url, url_ok, archive_url, sources }) => ({
		id,
		title,
		published,
		date_basis,
		organisation,
		url,
		url_ok,
		archive_url,
		sources
	}));
	node.data = JSON.parse(devalue.stringify(data));
	await route.fulfill({ response: real, body: [JSON.stringify(envelope), ...rest].join('\n') });
}

/** Load the actors index with the synthesized index, through client-side navigation. */
export async function openSynthIndex(page: Page) {
	await page.route('**/apt-explorer/data/actors/index.json', (r) =>
		r.fulfill({ contentType: 'application/json', body: JSON.stringify(synthIndex()) })
	);
	await page.route('**/apt-explorer/actors/synth-busy/__data.json*', serveSynthProfile);
	// The prerendered index inlines the sample's index.json, so the first
	// load cannot be intercepted. A client-side navigation fetches it.
	await page.goto('/apt-explorer/');
	await page.getByRole('navigation').getByRole('link', { name: 'Actors', exact: true }).click();
	await expect(page).toHaveURL(/\/apt-explorer\/actors\/$/);
	await expect(page.getByRole('list', { name: 'Actors' }).getByRole('listitem')).toHaveCount(SYNTH_ACTORS);
}
