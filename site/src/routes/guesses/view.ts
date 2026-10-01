/**
 * Pure helpers for the guesses page: the words it shows and the filter it
 * applies. They live outside the component so a test can pin them down
 * without rendering anything.
 */
import type { Guess, GuessBand, GuessLabel, MatchKind, Term, YearCount } from '$lib/data/types';

/** A share as a whole percent. A missing figure is n/a, never 0%. */
export const percentText = (x: number | null): string => (x == null ? 'n/a' : `${Math.round(x * 100)}%`);

const KIND_TEXT: Record<MatchKind, string> = {
	variant: 'Same name apart from a suffix or a plural',
	contains: 'One name contains the other',
	fuzzy: 'A close spelling'
};

export const kindText = (kind: MatchKind): string => KIND_TEXT[kind];

/** The confidence a guess needs to enter each band, as the evaluation text states them. */
export const BAND_THRESHOLDS = { medium: 0.7, high: 0.85 } as const;

export const LABELS: GuessLabel[] = ['actor', 'malware', 'tool', 'not-an-entity'];
export const BANDS: GuessBand[] = ['high', 'medium', 'low', 'unvalidated', 'confirmed'];

const LABEL_TEXT: Record<GuessLabel, string> = {
	actor: 'Actor',
	malware: 'Malware',
	tool: 'Tool',
	'not-an-entity': 'Not an entity'
};

const BAND_TEXT: Record<GuessBand, string> = {
	high: 'High',
	medium: 'Medium',
	low: 'Low',
	unvalidated: 'Unvalidated',
	confirmed: 'Confirmed'
};

export const labelText = (label: GuessLabel): string => LABEL_TEXT[label];
export const bandText = (band: GuessBand): string => BAND_TEXT[band];

/**
 * The band, with the measured confidence when the guess has one. A value
 * below 1 is never shown as 100%, because no guess here is certain.
 */
export function confidenceText(g: Guess): string {
	if (g.confidence == null) return bandText(g.band);
	const percent = g.confidence < 1 ? Math.min(99, Math.round(g.confidence * 100)) : 100;
	return `${bandText(g.band)}, ${percent}%`;
}

export interface Filter {
	label: GuessLabel | 'all';
	band: GuessBand | 'all';
	query: string;
}

/** The guesses that pass every filter, in their original order. */
export function filterGuesses(rows: Guess[], f: Filter): Guess[] {
	const q = f.query.trim().toLowerCase();
	return rows.filter(
		(g) =>
			(f.label === 'all' || g.label === f.label) &&
			(f.band === 'all' || g.band === f.band) &&
			(q === '' ||
				g.name.toLowerCase().includes(q) ||
				(g.matched_actor_name ?? '').toLowerCase().includes(q))
	);
}

/** How many rows fall under each key, with a zero for a key that never occurs. */
export function countBy<K extends string>(rows: Guess[], key: (g: Guess) => K, keys: K[]): Record<K, number> {
	const out = Object.fromEntries(keys.map((k) => [k, 0])) as Record<K, number>;
	for (const g of rows) out[key(g)] += 1;
	return out;
}

/** A signal's weight in words. Null and zero are context: they moved nothing. */
export function weightText(weight: number | null): string {
	if (weight == null || weight === 0) return 'context only';
	const n = weight.toFixed(1);
	return weight > 0 ? `+${n} supports the guess` : `${n} argues against it`;
}

/**
 * A kept signal's model weight as a direction and a strength. The model
 * separates actor from malware, so a positive weight points toward malware
 * and a negative weight toward actor. A bare signed number does not say that.
 */
export function directionText(weight: number | null): string | null {
	if (weight == null || weight === 0) return null;
	return `pushes toward ${weight > 0 ? 'malware' : 'actor'}, strength ${Math.abs(weight).toFixed(1)}`;
}

/**
 * Where the method stands against a plain alternative, in whole percentage
 * points. A gap under half a point counts as level, since the accuracy is
 * measured on a few dozen names and a smaller gap is noise.
 */
export function gainText(accuracy: number | null, baseline: number | null): string | null {
	if (accuracy == null || baseline == null) return null;
	const points = Math.round((accuracy - baseline) * 100);
	if (points === 0) return 'level with';
	return `${Math.abs(points)} points ${points > 0 ? 'above' : 'below'}`;
}

/** "3 reports from 2 publishers", each noun agreeing with its count. */
export function termCountText(t: Pick<Term, 'reports' | 'publishers'>): string {
	const r = t.reports === 1 ? 'report' : 'reports';
	const p = t.publishers === 1 ? 'publisher' : 'publishers';
	return `${t.reports} ${r} from ${t.publishers} ${p}`;
}

/** When a term was first and last seen, as one phrase. A single date stands alone. */
export function seenRangeText(first: string | null, last: string | null): string {
	if (first == null && last == null) return 'No date';
	if (first == null || last == null || first === last) return `Seen ${first ?? last}`;
	return `Seen ${first} to ${last}`;
}

/** The per-year counts as text, for a reader who does not see the bars. */
export function yearsText(years: YearCount[]): string {
	return years.map((y) => `${y.year}: ${y.count}`).join(', ');
}

/** Each year's bar as a share of the busiest year, never below a visible sliver. */
export function yearShares(years: YearCount[]): { year: number; count: number; share: number }[] {
	const max = Math.max(1, ...years.map((y) => y.count));
	return years.map((y) => ({ ...y, share: Math.max(0.06, y.count / max) }));
}

/** The terms whose name or guessed actor contains the query, in their original order. */
export function filterTerms(rows: Term[], query: string): Term[] {
	const q = query.trim().toLowerCase();
	if (q === '') return rows;
	return rows.filter(
		(t) => t.name.toLowerCase().includes(q) || (t.guess.matched_actor_name ?? '').toLowerCase().includes(q)
	);
}
