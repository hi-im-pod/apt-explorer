/**
 * Sorting a report's links into what they are: the publisher's own page, a
 * copy of it held by someone else, or a link whose publisher the site cannot
 * confirm.
 *
 * The distinction matters because the two are easy to confuse. About a third
 * of ORKL's library points at a collection on papers.vx-underground.org, which
 * is a third-party mirror. If the site labelled that address "original", a
 * reader would cite a mirror as though it were the publisher. So the site
 * decides what a link is from its host alone, never from the field it was
 * stored in, and a mirror is never given the original role.
 *
 * A host alone also cannot show that a link is the publisher's, when the host
 * serves other people's pages: a link shortener, a reference site such as
 * Wikipedia or ETDA, a file host or a cache. Those links get their own kind
 * and are never labelled original. Every other host is still labelled original
 * by rule, and the Methodology page says the rule can be wrong.
 *
 * This file is pure: no DOM, no fetch, so every host class is unit-tested.
 */

export type LinkKind =
	| 'publisher'
	| 'unconfirmed'
	| 'orkl-archive'
	| 'vxug-mirror'
	| 'cybermonitor-mirror'
	| 'box-mirror'
	| 'wayback'
	| 'archive-today'
	| 'invalid';

export interface LinkClass {
	kind: LinkKind;
	/** The full label shown in the detail panel. */
	label: string;
	/** A short label for the explore table, where width is scarce. */
	short: string;
	/** One plain sentence on what the link is, and what it is not. */
	explanation: string;
	/** The address parsed as an http or https URL. False for anything else. */
	valid: boolean;
	/** Where the link goes, without "www.", for showing beside the label. Empty when invalid. */
	host: string;
	/** A copy held by someone other than the publisher: an archive or a mirror. */
	copy: boolean;
	/** A copy that was collected by a third party, as opposed to an archive service. */
	mirror: boolean;
}

type ClassBody = Pick<LinkClass, 'kind' | 'label' | 'short' | 'explanation'> & {
	mirror?: boolean;
};

const PUBLISHER: ClassBody = {
	kind: 'publisher',
	label: 'Original publisher',
	short: 'Original',
	explanation: 'The address the source records as the place the report was published.'
};

const UNCONFIRMED: ClassBody = {
	kind: 'unconfirmed',
	label: 'Link, publisher not confirmed',
	short: 'Link',
	explanation:
		'A link on a site that serves other people’s pages, such as a link shortener, a reference page, a file host or a cache. The site cannot tell whether it is the publisher’s page or a copy.'
};

const ORKL_ARCHIVE: ClassBody = {
	kind: 'orkl-archive',
	label: 'Archived copy on ORKL',
	short: 'ORKL copy',
	explanation:
		'A saved copy of the report held by ORKL, a threat report library. It is not the publisher’s page.'
};

const VXUG: ClassBody = {
	kind: 'vxug-mirror',
	label: 'Mirror on VX-Underground',
	short: 'VX mirror',
	mirror: true,
	explanation:
		'A copy in the VX-Underground paper collection, a third-party site. It is not the publisher’s page.'
};

const CYBERMONITOR: ClassBody = {
	kind: 'cybermonitor-mirror',
	label: 'CyberMonitor archive on GitHub',
	short: 'CyberMonitor',
	mirror: true,
	explanation:
		'A copy in the CyberMonitor collection of threat reports on GitHub. It is not the publisher’s page.'
};

const BOX: ClassBody = {
	kind: 'box-mirror',
	label: 'Mirror on Box',
	short: 'Box mirror',
	mirror: true,
	explanation: 'A copy in a shared Box folder. It is not the publisher’s page.'
};

const WAYBACK: ClassBody = {
	kind: 'wayback',
	label: 'Wayback Machine',
	short: 'Wayback',
	explanation:
		'A snapshot saved by the Internet Archive. It shows the page as it was on the snapshot date, which may differ from the page today.'
};

const ARCHIVE_TODAY: ClassBody = {
	kind: 'archive-today',
	label: 'archive.today',
	short: 'archive.today',
	explanation:
		'A snapshot saved by archive.today. It shows the page as it was on the snapshot date, which may differ from the page today.'
};

const INVALID: ClassBody = {
	kind: 'invalid',
	label: 'Unreadable link',
	short: 'Link',
	explanation: 'This address could not be read as a web link, so where it goes is not known.'
};

/**
 * Every kind a readable address can get, in the order the About page lists
 * them. The page prints this list instead of retyping it, so the legend cannot
 * drift from the labels the panel shows.
 */
export const LINK_KINDS: readonly Pick<ClassBody, 'kind' | 'label' | 'explanation'>[] = [
	PUBLISHER,
	UNCONFIRMED,
	ORKL_ARCHIVE,
	VXUG,
	CYBERMONITOR,
	BOX,
	WAYBACK,
	ARCHIVE_TODAY
];

/** Hosts whose whole site is a copy collection, matched exactly or as a subdomain. */
const HOST_CLASSES: readonly (readonly [string, ClassBody])[] = [
	['vx-underground.org', VXUG],
	['archive.orkl.eu', ORKL_ARCHIVE],
	['app.box.com', BOX],
	['web.archive.org', WAYBACK],
	['archive.org', WAYBACK],
	['archive.ph', ARCHIVE_TODAY],
	['archive.is', ARCHIVE_TODAY],
	['archive.today', ARCHIVE_TODAY],
	// Hosts that serve other people's pages. An address here is not evidence of who wrote the report.
	['t.co', UNCONFIRMED],
	['bit.ly', UNCONFIRMED],
	['tinyurl.com', UNCONFIRMED],
	['goo.gl', UNCONFIRMED],
	['ow.ly', UNCONFIRMED],
	['lnkd.in', UNCONFIRMED],
	['buff.ly', UNCONFIRMED],
	['is.gd', UNCONFIRMED],
	['apt.etda.or.th', UNCONFIRMED],
	['malpedia.caad.fkie.fraunhofer.de', UNCONFIRMED],
	['wikipedia.org', UNCONFIRMED],
	['drive.google.com', UNCONFIRMED],
	['docs.google.com', UNCONFIRMED],
	['storage.googleapis.com', UNCONFIRMED],
	['webcache.googleusercontent.com', UNCONFIRMED],
	['dropbox.com', UNCONFIRMED],
	['dropboxusercontent.com', UNCONFIRMED],
	['mega.nz', UNCONFIRMED],
	['onedrive.live.com', UNCONFIRMED],
	['1drv.ms', UNCONFIRMED],
	['slideshare.net', UNCONFIRMED],
	['speakerdeck.com', UNCONFIRMED],
	['scribd.com', UNCONFIRMED],
	['pastebin.com', UNCONFIRMED],
	['telegra.ph', UNCONFIRMED],
	['academia.edu', UNCONFIRMED],
	['researchgate.net', UNCONFIRMED],
	['s3.amazonaws.com', UNCONFIRMED],
	['gist.github.com', UNCONFIRMED],
	['gist.githubusercontent.com', UNCONFIRMED],
	['virustotal.com', UNCONFIRMED]
];

/** Matches the host itself or a real subdomain, so "notvx-underground.org" does not match. */
function hostIs(host: string, domain: string): boolean {
	return host === domain || host.endsWith(`.${domain}`);
}

function build(body: ClassBody, host: string, valid: boolean): LinkClass {
	const copy = body.kind !== 'publisher' && body.kind !== 'invalid' && body.kind !== 'unconfirmed';
	return {
		kind: body.kind,
		label: body.label,
		short: body.short,
		explanation: body.explanation,
		valid,
		host,
		copy,
		mirror: body.mirror === true
	};
}

/**
 * Classify one address by its host. GitHub is a mirror only under the
 * CyberMonitor account, because the same host also serves publishers'
 * own repositories.
 */
export function classifyLink(href: string): LinkClass {
	let url: URL;
	try {
		url = new URL(href.trim());
	} catch {
		return build(INVALID, '', false);
	}
	if (url.protocol !== 'http:' && url.protocol !== 'https:') return build(INVALID, '', false);
	const host = url.hostname.toLowerCase().replace(/^www\./, '');
	if (!host) return build(INVALID, '', false);

	if (host === 'github.com' || host === 'raw.githubusercontent.com') {
		const account = url.pathname.split('/')[1]?.toLowerCase();
		if (account === 'cybermonitor') return build(CYBERMONITOR, host, true);
		return build(PUBLISHER, host, true);
	}
	for (const [domain, body] of HOST_CLASSES) {
		if (hostIs(host, domain)) return build(body, host, true);
	}
	return build(PUBLISHER, host, true);
}

/** The three link fields of a report, which is all this file needs to know about one. */
export interface ReportLinks {
	url: string | null;
	url_ok: boolean | null;
	archive_url: string | null;
}

export interface ReportLink {
	href: string;
	/** Original only for a link that is not an archive, a mirror or a host that cannot be confirmed. */
	role: 'original' | 'copy' | 'unconfirmed';
	class: LinkClass;
	/** The last link check failed for this address. */
	unreachable: boolean;
}

export type LinkSituation = 'both' | 'original-only' | 'copies-only' | 'unconfirmed' | 'none';

export interface LinkDescription {
	/** In the order a visitor should try them. */
	links: ReportLink[];
	situation: LinkSituation;
	/** One plain sentence saying what the visitor is looking at. */
	note: string;
}

const NO_ORIGINAL = 'No original publisher link is known;';

function copiesNote(copies: ReportLink[]): string {
	if (copies.length === 1) {
		return `${NO_ORIGINAL} this is ${copies[0].class.mirror ? 'a mirror' : 'an archived copy'}.`;
	}
	return `${NO_ORIGINAL} these are copies held by other services, not the publisher.`;
}

/**
 * Decide each link's role, its order, and the sentence that explains the
 * result. url_ok describes only the url field, so only that link can be
 * flagged unreachable. An unreachable original moves behind the copies,
 * and is kept, because the last check may have been wrong.
 */
export function describeLinks(report: ReportLinks): LinkDescription {
	const found: ReportLink[] = [];
	const add = (href: string | null, unreachable: boolean) => {
		if (!href) return;
		const cls = classifyLink(href);
		// A malformed address is dropped: it cannot be followed, and showing
		// it as a link would promise something the page cannot keep.
		if (!cls.valid) return;
		const role = cls.copy ? 'copy' : cls.kind === 'unconfirmed' ? 'unconfirmed' : 'original';
		found.push({ href, role, class: cls, unreachable });
	};
	add(report.url, report.url_ok === false);
	add(report.archive_url, false);

	const original = found.find((l) => l.role === 'original');
	const copies = found.filter((l) => l.role === 'copy');
	const unconfirmed = found.filter((l) => l.role === 'unconfirmed');
	const deadOriginal = original?.unreachable === true;
	const links = [...found].sort(byTrust);

	if (found.length === 0) return { links, situation: 'none', note: 'No link is recorded for this report.' };
	if (!original && unconfirmed.length > 0) {
		return { links, situation: 'unconfirmed', note: unconfirmedNote(unconfirmed, copies) };
	}
	if (!original) {
		const dead = copies.find((c) => c.unreachable);
		const extra = dead ? ` The ${dead.class.mirror ? 'mirror' : 'copy'} link was unreachable at the last link check.` : '';
		return { links, situation: 'copies-only', note: copiesNote(copies) + extra };
	}
	if (copies.length === 0) {
		const note = deadOriginal
			? 'The original link was unreachable at the last link check, and no copy is recorded.'
			: 'Only the original publisher link is known. No copy is recorded.';
		return { links, situation: 'original-only', note };
	}
	const note = deadOriginal
		? 'The original link was unreachable at the last link check, so the copy is listed first. The copy is a duplicate held by another service, not the publisher.'
		: 'The original publisher link goes to the site that published the report. The copy is a duplicate held by another service, so it can differ from the original or outlive it.';
	return { links, situation: 'both', note };
}

function unconfirmedNote(unconfirmed: ReportLink[], copies: ReportLink[]): string {
	const one = unconfirmed.length === 1;
	let note = 'No original publisher link is confirmed. ';
	note += one
		? 'This link goes to a site that does not publish reports itself, so it may not be the publisher.'
		: 'These links go to sites that do not publish reports themselves, so they may not be the publisher.';
	if (copies.length > 0) {
		note += copies.length === 1 ? ' The other link is a copy held by another service.' : ' The other links are copies held by other services.';
	}
	if (unconfirmed.some((l) => l.unreachable)) note += ' A link was unreachable at the last link check.';
	return note;
}

const RANK = { original: 0, unconfirmed: 1, copy: 2 } as const;

/**
 * Reachable before unreachable, then original, then a link the site cannot
 * confirm, then a copy, and otherwise the order the fields came in. A failed
 * link is kept but moved behind the rest.
 */
function byTrust(a: ReportLink, b: ReportLink): number {
	return Number(a.unreachable) - Number(b.unreachable) || RANK[a.role] - RANK[b.role];
}
