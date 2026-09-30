/**
 * What the home page works out from the data: the sample of names for the
 * alias grid, and two small pieces of wording. Pure, so each is unit-tested.
 */
import type { Actor, PublishPolicy, SourceKey } from './data/types';

export interface GridRow {
	name: string;
	sources: SourceKey[];
	/** The actor's own name, the row the grid opens with. */
	primary: boolean;
}

export interface AliasGrid {
	/** The sources that list at least one of the names, in the order sources.json gives them. */
	columns: SourceKey[];
	rows: GridRow[];
	/** Every name the actor has, shown or not. */
	total: number;
}

/**
 * A sample of an actor's names for the grid. The actor's own name comes first.
 * The other names are sorted from the most widely listed to the least, and the
 * sample takes evenly spaced names from that list, so the rows run from names
 * every source uses to names only one source uses. Taking the first names in
 * the data's order would show only the widely listed ones and hide the
 * disagreement the grid exists to show.
 */
export function aliasGrid(actor: Actor, sourceOrder: SourceKey[], limit = 12): AliasGrid {
	const used = new Set(actor.aliases.flatMap((a) => a.sources));
	const columns = [
		...sourceOrder.filter((k) => used.has(k)),
		...[...used].filter((k) => !sourceOrder.includes(k)).sort()
	];
	const own = actor.aliases.find((a) => a.value === actor.name);
	const others = actor.aliases
		.filter((a) => a !== own)
		.map((a, i) => ({ a, i }))
		.sort((x, y) => y.a.sources.length - x.a.sources.length || x.i - y.i)
		.map(({ a }) => a);

	const want = Math.max(0, limit - 1);
	const picked =
		others.length <= want
			? others
			: Array.from({ length: want }, (_, i) =>
					others[want === 1 ? 0 : Math.floor((i * (others.length - 1)) / (want - 1))]
				);

	const rows: GridRow[] = [
		{ name: actor.name, sources: own?.sources ?? [], primary: true },
		...picked.map((a) => ({ name: a.value, sources: a.sources, primary: false }))
	];
	return { columns, rows, total: actor.aliases.length };
}

const ONES = [
	'zero',
	'one',
	'two',
	'three',
	'four',
	'five',
	'six',
	'seven',
	'eight',
	'nine',
	'ten',
	'eleven',
	'twelve',
	'thirteen',
	'fourteen',
	'fifteen',
	'sixteen',
	'seventeen',
	'eighteen',
	'nineteen'
];
const TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'];

/** 46 as "forty-six". Above 99 a number reads better as digits, so those come back as digits. */
export function numberWord(n: number): string {
	if (!Number.isInteger(n) || n < 0 || n > 99) return String(n);
	if (n < 20) return ONES[n];
	const t = TENS[Math.floor(n / 10)];
	return n % 10 ? `${t}-${ONES[n % 10]}` : t;
}

/** What each publish policy lets the site show, in a few words for a table cell. */
export const PUBLISH_SHORT: Readonly<Record<PublishPolicy, string>> = {
	full: 'Full',
	'derived-only': 'Derived facts only',
	'link-only': 'Links only',
	'evidence-only': 'Evidence only'
};

export function publishShort(policy: PublishPolicy): string {
	return PUBLISH_SHORT[policy] ?? policy;
}
