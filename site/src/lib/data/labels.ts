/**
 * Display text for values the data stores as keys.
 *
 * sources.json names each source by its connector key ("dfir"), never by a
 * display name, so the site owns the names. They follow SOURCES.md. Names
 * carry no ® because headings reuse them; MITRE asks for the sign at the
 * first mention in running text only, and page copy adds it there.
 */
import type { PublishPolicy, SourceKey } from './types';

export interface SourceLabel {
	/** The name for running text, tables and headings. */
	name: string;
	/** A compact form for badges and narrow columns. */
	short: string;
	/** What the site takes from the source, in a few words. */
	role: string;
}

export const SOURCE_LABELS: Readonly<Record<SourceKey, SourceLabel>> = {
	attack: {
		name: 'MITRE ATT&CK',
		short: 'ATT&CK',
		role: 'Groups, aliases, campaigns, techniques and software.'
	},
	misp: {
		name: 'MISP galaxy threat-actor cluster',
		short: 'MISP',
		role: 'Actors, synonyms, origin, sponsor and claimed targets.'
	},
	etda: {
		name: 'ETDA Threat Group Cards',
		short: 'ETDA',
		role: 'Actor names, aliases and short values such as origin.'
	},
	malpedia: {
		name: 'Malpedia',
		short: 'Malpedia',
		role: 'Links from actors to malware families and reports, and report dates.'
	},
	orkl: {
		name: 'ORKL',
		short: 'ORKL',
		role: 'Report titles, dates and links. Its actor tags are used only as matching evidence.'
	},
	kev: {
		name: 'CISA Known Exploited Vulnerabilities Catalog',
		short: 'CISA KEV',
		role: 'Exploited CVEs, the date each was added and the ransomware flag.'
	},
	dfir: {
		name: 'The DFIR Report',
		short: 'DFIR Report',
		role: 'Titles, dates and links for intrusion write-ups.'
	},
	paper: {
		name: "Yuldoshkhujaev et al., CCS '25 dataset",
		short: "CCS '25 data",
		role: 'A labelled historical layer for 2014 to 2023.'
	}
};

/** The label for a source key, or the key itself for a source added since. */
export function sourceLabel(key: SourceKey): SourceLabel {
	return SOURCE_LABELS[key] ?? { name: key, short: key, role: '' };
}

/**
 * What each publish policy lets the site show, in the words the About and
 * Methodology pages use. SOURCES.md holds the full rule for each.
 */
export const PUBLISH_POLICIES: Readonly<Record<PublishPolicy, string>> = {
	full: 'Every field the pipeline takes from the source may appear, with a source badge and its provenance.',
	'derived-only':
		"Short factual values may appear with a source badge: names, aliases, country and sector values, motivation, dates and identifiers. The source's own text is never copied. The licence duties still apply in full.",
	'link-only':
		"Only each item's title, publisher, publication date and link appear, plus identifiers this project computes itself, such as a content hash.",
	'evidence-only':
		'Nothing from the source appears in the published data. The source only adds evidence when the registry decides whether two actor names belong to the same actor, and the site reports that evidence as a count.'
};
