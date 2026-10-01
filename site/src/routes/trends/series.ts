/**
 * Turns trends.json into the series the trends charts draw.
 *
 * Everything here is pure and unit-tested, so the charts only draw. Two
 * rules hold for every time series:
 *
 * - Nothing before window_start is drawn. The pipeline already leaves it
 *   out; dropping it again here means a bad build cannot stretch an axis
 *   back into the paper's years.
 * - Periods with no data are filled with zero up to the build date. A gap
 *   in a bar chart would otherwise look like a missing bar, not a zero.
 *
 * Dates are read digit by digit and built with Date.UTC, never parsed by
 * the Date constructor, so the result is the same in every time zone.
 */
import type { IsoDate, Month, Quarter, Trends } from '$lib/data/types';

/** "2024-05-01" or "2024-05-01T03:00:00Z" to "2024-Q2". */
export function quarterOf(date: IsoDate | string): Quarter {
	const year = date.slice(0, 4);
	const month = Number(date.slice(5, 7));
	return `${year}-Q${Math.ceil(month / 3)}`;
}

/** "2024-05-01" or "2024-05-01T03:00:00Z" to "2024-05". */
export function monthOf(date: IsoDate | string): Month {
	return date.slice(0, 7);
}

function quarterParts(q: Quarter): [number, number] {
	return [Number(q.slice(0, 4)), Number(q.slice(6))];
}

function monthParts(m: Month): [number, number] {
	return [Number(m.slice(0, 4)), Number(m.slice(5, 7))];
}

/** The first moment of a quarter, in UTC. */
export function quarterStart(q: Quarter): Date {
	const [y, n] = quarterParts(q);
	return new Date(Date.UTC(y, (n - 1) * 3, 1));
}

/** The first moment of the quarter after this one, in UTC. */
export function quarterEnd(q: Quarter): Date {
	const [y, n] = quarterParts(q);
	return new Date(Date.UTC(y, n * 3, 1));
}

/** The first moment of a month, in UTC. */
export function monthStart(m: Month): Date {
	const [y, n] = monthParts(m);
	return new Date(Date.UTC(y, n - 1, 1));
}

/** The first moment of the month after this one, in UTC. */
export function monthEnd(m: Month): Date {
	const [y, n] = monthParts(m);
	return new Date(Date.UTC(y, n, 1));
}

/** Every quarter from `from` to `to`, both included; empty when `to` is earlier. */
export function quarterRange(from: Quarter, to: Quarter): Quarter[] {
	const out: Quarter[] = [];
	let [y, n] = quarterParts(from);
	const [ty, tn] = quarterParts(to);
	while (y < ty || (y === ty && n <= tn)) {
		out.push(`${y}-Q${n}`);
		n += 1;
		if (n > 4) {
			n = 1;
			y += 1;
		}
	}
	return out;
}

/** Every month from `from` to `to`, both included; empty when `to` is earlier. */
export function monthRange(from: Month, to: Month): Month[] {
	const out: Month[] = [];
	let [y, n] = monthParts(from);
	const [ty, tn] = monthParts(to);
	while (y < ty || (y === ty && n <= tn)) {
		out.push(`${y}-${String(n).padStart(2, '0')}`);
		n += 1;
		if (n > 12) {
			n = 1;
			y += 1;
		}
	}
	return out;
}

/** The later of two sortable period strings. */
const later = (a: string, b: string) => (a > b ? a : b);

// ---------------------------------------------------------------------------
// Reporting activity

export interface ActivityPoint {
	actor: string;
	quarter: Quarter;
	start: Date;
	end: Date;
	count: number;
	/** Reports in the same quarter a year earlier. */
	prev: number;
}

export interface Activity {
	/** The most reported actors in the window, most reported first. */
	actors: string[];
	quarters: Quarter[];
	/** One point per actor and quarter, zero-filled. */
	points: ActivityPoint[];
}

/**
 * Reports per quarter for the `top` most reported actors, from the window
 * start to the quarter of the build. Actors are ranked by reports inside
 * the window only, with ties broken by ID so the order is stable.
 */
export function reportingActivity(t: Trends, top: number): Activity {
	const first = quarterOf(t.window_start);
	const rows = t.reporting_activity.filter((r) => r.quarter >= first);
	const last = rows.reduce((q, r) => later(q, r.quarter), quarterOf(t.generated_at));
	const quarters = quarterRange(first, last);

	const totals = new Map<string, number>();
	for (const r of rows) totals.set(r.actor, (totals.get(r.actor) ?? 0) + r.count);
	const actors = [...totals]
		.filter(([, n]) => n > 0)
		.sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
		.slice(0, top)
		.map(([id]) => id);

	const byKey = new Map(rows.map((r) => [`${r.actor} ${r.quarter}`, r]));
	const points = actors.flatMap((actor) =>
		quarters.map((quarter) => {
			const r = byKey.get(`${actor} ${quarter}`);
			return {
				actor,
				quarter,
				start: quarterStart(quarter),
				end: quarterEnd(quarter),
				count: r?.count ?? 0,
				prev: r?.prev_year_count ?? 0
			};
		})
	);
	return { actors, quarters, points };
}

// ---------------------------------------------------------------------------
// KEV additions

export interface KevPoint {
	month: Month;
	start: Date;
	end: Date;
	added: number;
	ransomware: number;
	/** Additions without known ransomware use. */
	other: number;
}

/** KEV additions per month from the window start to the month of the build. */
export function kevMonthly(t: Trends): KevPoint[] {
	const first = monthOf(t.window_start);
	const rows = t.kev_monthly.filter((r) => r.month >= first);
	const last = rows.reduce((m, r) => later(m, r.month), monthOf(t.generated_at));
	const byMonth = new Map(rows.map((r) => [r.month, r]));
	return monthRange(first, last).map((month) => {
		const r = byMonth.get(month);
		const added = r?.added ?? 0;
		const ransomware = Math.min(r?.ransomware ?? 0, added);
		return {
			month,
			start: monthStart(month),
			end: monthEnd(month),
			added,
			ransomware,
			other: added - ransomware
		};
	});
}

// ---------------------------------------------------------------------------
// Reported versus documented techniques

export interface TechniqueBar {
	actor: string;
	/** Techniques in recent reports that ATT&CK does not list for the actor. */
	reportedOnly: number;
	/** Techniques in recent reports that ATT&CK also lists. */
	overlap: number;
	ids: string[];
}

/**
 * The `top` actors whose recent reports name techniques ATT&CK does not
 * document for them, most such techniques first, then by overlap. Actors
 * with nothing in either group have nothing to compare and are left out.
 */
export function reportedVsDocumented(t: Trends, top: number): TechniqueBar[] {
	return t.reported_vs_documented
		.map((r) => ({
			actor: r.actor,
			reportedOnly: r.reported_only.length,
			overlap: r.overlap,
			ids: r.reported_only
		}))
		.filter((b) => b.reportedOnly + b.overlap > 0)
		.sort(
			(a, b) =>
				b.reportedOnly - a.reportedOnly || b.overlap - a.overlap || (a.actor < b.actor ? -1 : 1)
		)
		.slice(0, top);
}

// ---------------------------------------------------------------------------
// Newly documented actors

export interface MonthCount {
	month: Month;
	start: Date;
	end: Date;
	count: number;
}

/** The new-actors window in months, mirroring the pipeline's 365-day rule. Prose reads its length from here. */
export const NEW_ACTOR_MONTHS = 12;

/**
 * New actors per month, over NEW_ACTOR_MONTHS up to the build. The range
 * never starts before the window.
 */
export function newActorMonths(t: Trends): MonthCount[] {
	const lastMonth = monthOf(t.generated_at);
	const [y, n] = monthParts(lastMonth);
	const twelveBack = monthOf(new Date(Date.UTC(y, n - NEW_ACTOR_MONTHS, 1)).toISOString());
	const first = later(twelveBack, monthOf(t.window_start));
	const counts = new Map<Month, number>();
	for (const a of t.new_actors) {
		const m = monthOf(a.first_seen);
		counts.set(m, (counts.get(m) ?? 0) + 1);
	}
	return monthRange(first, lastMonth).map((month) => ({
		month,
		start: monthStart(month),
		end: monthEnd(month),
		count: counts.get(month) ?? 0
	}));
}
