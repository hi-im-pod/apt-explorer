/**
 * Which time-axis ticks to label, and what each label says.
 *
 * A monthly or quarterly chart has more periods than a phone screen has room
 * to name. Labelling only January, as the first version did, left a reader
 * counting bars to find "March". This picks the densest set of ticks whose
 * labels do not touch, so a wide chart names every period and a narrow one
 * names every second, third or sixth. It is pure so that the spacing rule can
 * be unit-tested without a browser.
 */

export type TickKind = 'month' | 'quarter';

export interface TickRoom {
	/** The plot's width in px, without margins. */
	plotWidth: number;
	/** Free space to the left of the plot, which the first label may use. */
	leftRoom: number;
	/** Free space to the right of the plot, which the last label may use. */
	rightRoom: number;
}

export interface Ticks {
	ticks: Date[];
	/** The label for a tick returned in `ticks`. */
	format: (d: Date) => string;
}

/**
 * Px per character of a tick label. It is a little above the real advance of
 * the data font at 12px, so a fallback font that runs wider still fits.
 */
export const CHAR_PX = 7.6;
/** The smallest clear space between two neighbouring labels. */
const GAP_PX = 8;

const STEPS: Record<TickKind, number[]> = { month: [1, 2, 3, 4, 6, 12], quarter: [1, 2, 4] };
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function plainLabel(d: Date, kind: TickKind): string {
	return kind === 'month' ? MONTHS[d.getUTCMonth()] : `Q${Math.floor(d.getUTCMonth() / 3) + 1}`;
}

/**
 * The first tick and the first tick of each later year carry the year, so a
 * reader can always place a label in time without every label being long.
 */
function labelled(starts: Date[], indices: number[], kind: TickKind): string[] {
	let shownYear: number | null = null;
	return indices.map((i) => {
		const d = starts[i];
		const y = d.getUTCFullYear();
		const label = y === shownYear ? plainLabel(d, kind) : `${plainLabel(d, kind)} ${y}`;
		shownYear = y;
		return label;
	});
}

const width = (label: string) => label.length * CHAR_PX;

export function pickTicks(starts: Date[], kind: TickKind, room: TickRoom): Ticks {
	if (starts.length === 0) return { ticks: [], format: () => '' };
	const pitch = room.plotWidth / starts.length;

	let indices: number[] = [];
	let labels: string[] = [];
	for (const step of STEPS[kind]) {
		indices = starts.map((_, i) => i).filter((i) => i % step === 0);
		labels = labelled(starts, indices, kind);
		const fits = indices.every(
			(idx, k) =>
				k === 0 ||
				(idx - indices[k - 1]) * pitch >= (width(labels[k - 1]) + width(labels[k])) / 2 + GAP_PX
		);
		if (fits) break;
	}

	// A label centred on a tick near the right end would be cut off, so those ticks are dropped.
	const keep = indices.map((idx, k) => idx * pitch + width(labels[k]) / 2 <= room.plotWidth + room.rightRoom);
	indices = indices.filter((_, k) => keep[k]);
	labels = labels.filter((_, k) => keep[k]);
	// Keep at least the first tick, which is the window start.
	if (indices.length === 0) {
		indices = [0];
		labels = labelled(starts, [0], kind);
	}

	const byTime = new Map(indices.map((idx, k) => [starts[idx].getTime(), labels[k]]));
	return {
		ticks: indices.map((i) => starts[i]),
		format: (d: Date) => byTime.get(d.getTime()) ?? plainLabel(d, kind)
	};
}
