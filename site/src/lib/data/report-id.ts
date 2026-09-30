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

/** A report id in the form the index stores. Ids that are not digests are kept whole. */
export function shortId(id: string, idLen: number): string {
	return SHA.test(id) ? id.slice(0, idLen) : id;
}

/**
 * The index form of an id taken from a link. Actor pages link with the full
 * id, so a full digest is cut the same way the index cuts it. Anything else
 * is returned as it is: it is either already short or not a digest.
 */
export function indexForm(param: string, idLen: number): string {
	return shortId(param, idLen);
}
