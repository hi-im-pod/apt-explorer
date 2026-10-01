/**
 * Formatting shared by every page.
 *
 * Nothing here uses toLocale* or the Date parser. Prerender runs in Node and
 * hydration runs in the visitor's browser, with its own locale and time
 * zone; if the two produced different text, the page would change after
 * load. The data's dates are calendar dates or UTC timestamps, so reading
 * the digits is both exact and the same everywhere.
 */
import { numberWord } from './home';

const MONTHS = [
	'January',
	'February',
	'March',
	'April',
	'May',
	'June',
	'July',
	'August',
	'September',
	'October',
	'November',
	'December'
];

/** "2026-09-28" or "2026-09-28T03:21:05Z" to "28 September 2026" (the UTC date). */
export function formatDate(value: string | null): string {
	if (value == null) return 'not reported';
	const m = /^(\d{4})-(\d{2})-(\d{2})(?:T|$)/.exec(value);
	const month = m ? MONTHS[Number(m[2]) - 1] : undefined;
	if (!m || !month) throw new Error(`Not a date: ${value}`);
	return `${Number(m[3])} ${month} ${m[1]}`;
}

/** 29538 to "29,538". */
export function formatCount(n: number): string {
	return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

/** 24 as "two years", 18 as "eighteen months". Whole years from two up read better as years. */
export function spanInWords(months: number): string {
	return months >= 24 && months % 12 === 0 ? `${numberWord(months / 12)} years` : `${numberWord(months)} months`;
}

/** "the last two years" from the build's window, or "the recent window" when no build was read. */
export function lastSpan(months: number | null | undefined): string {
	return months ? `the last ${spanInWords(months)}` : 'the recent window';
}
