/**
 * Search, sort and display helpers for the actors index and profiles.
 *
 * They are plain functions so the rules can be unit-tested without a
 * browser, and so the prerendered page and the hydrated page compute the
 * same thing: nothing here depends on the visitor's locale.
 */
import type { ActorsIndexEntry } from '$lib/data';

/**
 * The form of a name that search compares. It follows the registry's own
 * normalization closely enough that a visitor typing "fancy-bear",
 * "APT 28" or a full-width name finds the actor: NFKC folds full-width
 * letters, and everything except letters and digits is dropped. Digits
 * stay, so "apt2" still narrows differently from "apt28".
 */
export function searchKey(value: string): string {
	return value
		.normalize('NFKC')
		.toLowerCase()
		.replace(/[^\p{L}\p{N}]+/gu, '');
}

/**
 * Whether an index entry matches a query, and through which alias.
 *
 * Returns null for no match. `via` is null when the name or ID matched (or
 * the query is blank), and otherwise holds the first alias that matched, so
 * the row can show why an actor with an unfamiliar name is in the results.
 */
export function matchActor(entry: ActorsIndexEntry, query: string): { via: string | null } | null {
	const q = searchKey(query);
	if (!q) return { via: null };
	if (searchKey(entry.name).includes(q) || searchKey(entry.id).includes(q)) return { via: null };
	const alias = entry.aliases.find((a) => searchKey(a).includes(q));
	return alias === undefined ? null : { via: alias };
}

export type ActorOrder = 'recent' | 'reports' | 'name';

// localeCompare would depend on the ICU data in Node at prerender and in the
// visitor's browser, and a different order after hydration would reshuffle
// the list under the reader. Lower-casing and comparing code units is the
// same everywhere.
function byName(a: ActorsIndexEntry, b: ActorsIndexEntry): number {
	const x = a.name.toLowerCase();
	const y = b.name.toLowerCase();
	return x < y ? -1 : x > y ? 1 : 0;
}

/** A sorted copy. Ties fall back to the name, so the order is stable across builds. */
export function sortActors(entries: readonly ActorsIndexEntry[], order: ActorOrder): ActorsIndexEntry[] {
	const out = [...entries];
	if (order === 'name') return out.sort(byName);
	if (order === 'reports') return out.sort((a, b) => b.report_count - a.report_count || byName(a, b));
	// ISO dates compare correctly as strings. An actor with no dated report
	// has nothing recent to sort by, so it goes after every dated one.
	return out.sort((a, b) => {
		if (a.last_reported === b.last_reported) return byName(a, b);
		if (a.last_reported === null) return 1;
		if (b.last_reported === null) return -1;
		return a.last_reported < b.last_reported ? 1 : -1;
	});
}

/**
 * Names for the ISO 3166-1 alpha-2 codes that sources give as an actor's
 * origin or a claimed target. Intl.DisplayNames would cover every code, but
 * its output comes from the ICU data of whichever runtime renders the page,
 * and prerender (Node) and hydration (the browser) could disagree. The list
 * covers the codes seen in the sources; an unknown code is shown as it is.
 */
const COUNTRY_NAMES: Readonly<Record<string, string>> = {
	AE: 'United Arab Emirates',
	AF: 'Afghanistan',
	AM: 'Armenia',
	AR: 'Argentina',
	AT: 'Austria',
	AU: 'Australia',
	AZ: 'Azerbaijan',
	BD: 'Bangladesh',
	BE: 'Belgium',
	BG: 'Bulgaria',
	BH: 'Bahrain',
	BR: 'Brazil',
	BY: 'Belarus',
	CA: 'Canada',
	CH: 'Switzerland',
	CL: 'Chile',
	CN: 'China',
	CO: 'Colombia',
	CU: 'Cuba',
	CZ: 'Czechia',
	DE: 'Germany',
	DK: 'Denmark',
	DZ: 'Algeria',
	EE: 'Estonia',
	EG: 'Egypt',
	ES: 'Spain',
	FI: 'Finland',
	FR: 'France',
	GB: 'United Kingdom',
	GE: 'Georgia',
	GR: 'Greece',
	HK: 'Hong Kong',
	HU: 'Hungary',
	ID: 'Indonesia',
	IE: 'Ireland',
	IL: 'Israel',
	IN: 'India',
	IQ: 'Iraq',
	IR: 'Iran',
	IT: 'Italy',
	JO: 'Jordan',
	JP: 'Japan',
	KG: 'Kyrgyzstan',
	KH: 'Cambodia',
	KP: 'North Korea',
	KR: 'South Korea',
	KW: 'Kuwait',
	KZ: 'Kazakhstan',
	LB: 'Lebanon',
	LK: 'Sri Lanka',
	LT: 'Lithuania',
	LV: 'Latvia',
	LY: 'Libya',
	MA: 'Morocco',
	MD: 'Moldova',
	MM: 'Myanmar',
	MX: 'Mexico',
	MY: 'Malaysia',
	NG: 'Nigeria',
	NL: 'Netherlands',
	NO: 'Norway',
	NP: 'Nepal',
	NZ: 'New Zealand',
	OM: 'Oman',
	PH: 'Philippines',
	PK: 'Pakistan',
	PL: 'Poland',
	PS: 'Palestine',
	PT: 'Portugal',
	QA: 'Qatar',
	RO: 'Romania',
	RS: 'Serbia',
	RU: 'Russia',
	SA: 'Saudi Arabia',
	SE: 'Sweden',
	SG: 'Singapore',
	SY: 'Syria',
	TH: 'Thailand',
	TJ: 'Tajikistan',
	TN: 'Tunisia',
	TR: 'Turkey',
	TW: 'Taiwan',
	UA: 'Ukraine',
	US: 'United States',
	UZ: 'Uzbekistan',
	VE: 'Venezuela',
	VN: 'Vietnam',
	YE: 'Yemen',
	ZA: 'South Africa'
};

/** "KP" to "North Korea"; anything else comes back unchanged. */
export function countryName(value: string): string {
	return COUNTRY_NAMES[value] ?? value;
}
