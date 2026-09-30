import { formatCount } from '$lib/format';

export const PAGE_SIZES = [25, 50, 100] as const;
export const DEFAULT_SIZE = 25;

export interface Paging {
	page: number;
	size: number;
}

/** The page and size in a query string. Anything malformed falls back on the default. */
export function parsePaging(params: URLSearchParams): Paging {
	const rawPage = params.get('page') ?? '';
	const page = /^[1-9]\d{0,8}$/.test(rawPage) ? Number(rawPage) : 1;
	const size = Number(params.get('size'));
	return { page, size: (PAGE_SIZES as readonly number[]).includes(size) ? size : DEFAULT_SIZE };
}

export function pageCount(total: number, size: number): number {
	return Math.max(1, Math.ceil(total / size));
}

export function clampPage(page: number, total: number, size: number): number {
	return Math.min(Math.max(1, page), pageCount(total, size));
}

export function pageOfIndex(index: number, size: number): number {
	return Math.floor(index / size) + 1;
}

/**
 * The page numbers to show: the first, the last, and the current page with its neighbours.
 * A gap that would hide only one page shows that page instead, since "…" saves no room.
 */
export function pageWindow(current: number, count: number): (number | 'gap')[] {
	const keep = new Set([1, count, current - 1, current, current + 1].filter((n) => n >= 1 && n <= count));
	const sorted = [...keep].sort((a, b) => a - b);
	const out: (number | 'gap')[] = [];
	for (let i = 0; i < sorted.length; i++) {
		const n = sorted[i];
		if (i > 0) {
			const gap = n - sorted[i - 1] - 1;
			if (gap === 1) out.push(n - 1);
			else if (gap > 1) out.push('gap');
		}
		out.push(n);
	}
	return out;
}

export function rangeLabel(page: number, size: number, total: number): string {
	if (total === 0) return 'No rows match';
	const first = (page - 1) * size + 1;
	const last = Math.min(page * size, total);
	return `Rows ${formatCount(first)} to ${formatCount(last)} of ${formatCount(total)} matching`;
}

/** A copy of `params` with the page and size set. Defaults are left out of the address. */
export function withPaging(params: URLSearchParams, { page, size }: Paging): URLSearchParams {
	const next = new URLSearchParams(params);
	next.delete('page');
	next.delete('size');
	if (page > 1) next.set('page', String(page));
	if (size !== DEFAULT_SIZE) next.set('size', String(size));
	return next;
}
