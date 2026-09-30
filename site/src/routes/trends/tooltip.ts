/**
 * The tooltip every trends chart shares.
 *
 * Plot's own tip is drawn inside the chart's SVG, so it is cut off at the
 * chart's edge and grows with its longest line. This one is an HTML box that
 * is measured after it is filled, then kept inside the chart on all four
 * sides. A mouse shows it while hovering. A finger shows it on tap and keeps
 * it until the next tap, because a lifted finger cannot hover.
 */
import type { ChartContext } from '$lib/components/Chart.svelte';

export interface Box {
	x: number;
	y: number;
	w: number;
	h: number;
}

export interface Hit {
	/** The first line is the title and is drawn bold. */
	text: string;
	/** The mark under the pointer, in px from the chart's top-left corner. */
	box: Box;
}

/** Finds the mark under a point given in px from the chart's top-left corner. */
export type Pick = (x: number, y: number) => Hit | null;

const TIP_MAX = 260;
const GAP = 6;

export function withTooltip(svg: Element, ctx: ChartContext, pick: Pick): HTMLElement {
	const wrap = document.createElement('div');
	wrap.style.cssText = 'position:relative;touch-action:pan-y;';
	(svg as SVGElement).style.display = 'block';

	const outline = document.createElement('div');
	outline.style.cssText = `position:absolute;display:none;pointer-events:none;box-sizing:border-box;border:2px solid ${ctx.text};border-radius:3px;`;

	const tip = document.createElement('div');
	tip.setAttribute('aria-hidden', 'true');
	tip.dataset.chartTip = '';
	tip.style.cssText = [
		'position:absolute',
		'display:none',
		'left:0',
		'top:0',
		'z-index:2',
		'pointer-events:none',
		'box-sizing:border-box',
		'width:max-content',
		`max-width:${Math.max(120, Math.min(TIP_MAX, ctx.width - 8))}px`,
		'padding:6px 8px',
		'border-radius:4px',
		`border:1px solid ${ctx.grid}`,
		`background:${ctx.background}`,
		`color:${ctx.text}`,
		`font:12px/1.4 ${ctx.font}`,
		'overflow-wrap:anywhere',
		'box-shadow:0 2px 8px rgba(0,0,0,0.25)'
	].join(';');

	wrap.append(svg, outline, tip);

	const hide = () => {
		tip.style.display = 'none';
		outline.style.display = 'none';
	};

	const show = (hit: Hit) => {
		const { box } = hit;
		tip.replaceChildren(
			...hit.text.split('\n').map((line, i) => {
				const row = document.createElement('div');
				row.textContent = line;
				if (i === 0) row.style.fontWeight = '600';
				return row;
			})
		);
		Object.assign(outline.style, {
			display: 'block',
			left: `${box.x}px`,
			top: `${box.y}px`,
			width: `${box.w}px`,
			height: `${box.h}px`
		});
		tip.style.display = 'block';

		const room = { w: wrap.clientWidth, h: wrap.clientHeight };
		const w = tip.offsetWidth;
		const h = tip.offsetHeight;
		const left = Math.min(Math.max(0, box.x + box.w / 2 - w / 2), Math.max(0, room.w - w));
		let top = box.y - h - GAP;
		if (top < 0) top = box.y + box.h + GAP;
		top = Math.min(Math.max(0, top), Math.max(0, room.h - h));
		tip.style.left = `${left}px`;
		tip.style.top = `${top}px`;
	};

	const at = (e: PointerEvent) => {
		const r = svg.getBoundingClientRect();
		const hit = pick(e.clientX - r.left, e.clientY - r.top);
		if (hit) show(hit);
		else hide();
	};

	wrap.addEventListener('pointermove', at);
	wrap.addEventListener('pointerdown', at);
	wrap.addEventListener('pointerleave', (e) => {
		if (e.pointerType === 'mouse') hide();
	});

	// A tap anywhere else closes a tip that a finger opened. The listener
	// removes itself once a redraw has replaced this chart.
	const outside = (e: PointerEvent) => {
		if (!wrap.isConnected) {
			document.removeEventListener('pointerdown', outside);
			return;
		}
		if (!wrap.contains(e.target as Node)) hide();
	};
	document.addEventListener('pointerdown', outside);

	return wrap;
}

/** The hit for the mark nearest to `x` among evenly or unevenly spaced slots given as [x1, x2] px ranges. */
export function nearestSlot(slots: Array<[number, number]>, x: number): number {
	let best = 0;
	let gap = Infinity;
	slots.forEach(([a, b], i) => {
		const d = x < a ? a - x : x > b ? x - b : 0;
		if (d < gap) {
			gap = d;
			best = i;
		}
	});
	return best;
}
