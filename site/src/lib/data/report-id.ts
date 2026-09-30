/**
 * How a report id is written in the index and in links.
 *
 * The full ids are 40 hex characters, and there are thirty thousand of them,
 * which would be a fifth of the index. The index stores each one cut to
 * `id_len` characters (the pipeline picks the shortest length that is unique,
 * never under eight), and the page writes that short form in `?report=`.
 * This file mirrors `short_id` in pipeline/aptx/build/report_index.py.
 */

const SHA = /^[0-9a-f]{40}$/;
const HEX = /^[0-9a-f]+$/;

/** A report id in the form the index stores. Ids that are not digests are kept whole. */
export function shortId(id: string, idLen: number): string {
	return SHA.test(id) ? id.slice(0, idLen) : id;
}

/**
 * The index form of an id taken from a link. Actor pages link with the full
 * id, and a link saved under an older build may carry a longer prefix than
 * this build's index, so any hex text at least `idLen` long is cut the way
 * the index cuts it. Anything else is returned as it is: it is either
 * shorter (see `search.ts` for that case) or not a digest.
 */
export function indexForm(param: string, idLen: number): string {
	return HEX.test(param) && param.length >= idLen && param.length <= 40 ? param.slice(0, idLen) : param;
}
