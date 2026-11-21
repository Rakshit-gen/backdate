// Layout and geometry for the invalidation graph. Logical space is W x H with y pointing down.
import { affectedBy, day, monthOf, overlaps, yearFraction } from "./scene";
import type { Changeset, Graph, Read } from "./types";

export const W = 1000;
export const H = 540;
export const LEFT = 128;
export const RIGHT = 984;
export const LANE_Y0 = 46;
export const LANE_GAP = 40;
export const GROSS_Y = 316;
export const WH_Y = 446;
export const NODE_R = 11;

const FIRST_ATTRS = ["annual_salary_cents", "fte_bp", "state"];

export const monthX = (m: number) => LEFT + ((m + 0.5) * (RIGHT - LEFT)) / 12;
export const dateX = (iso: string | null) => LEFT + yearFraction(iso) * (RIGHT - LEFT);

export type Lane = { entity: string; attribute: string; y: number };
export type NodeSpec = { id: number; derivation: string; key: string; x: number; y: number; depth: number | null };
export type EdgeSpec = { points: [number, number][]; start: number; width: number; dur?: number };
export type Changed = { lane: Lane; x0: number; x1: number };

export const TIMING = { factToNode: 0.25, edge: 0.75, node: 0.35, derived: 0.55 };

/** Start time of the ink in an edge into a node at this depth. */
const edgeStart = (depth: number) =>
  depth === 0
    ? TIMING.factToNode
    : TIMING.factToNode + TIMING.edge + TIMING.node + (depth - 1) * (TIMING.derived + TIMING.node);
const edgeDur = (depth: number) => (depth === 0 ? TIMING.edge : TIMING.derived);
export const nodeStart = (depth: number) => edgeStart(depth) + edgeDur(depth);

export function lanesOf(graph: Graph): Lane[] {
  const seen = new Map<string, { entity: string; attribute: string }>();
  for (const c of graph.computations) for (const r of c.reads) seen.set(`${r.entity}|${r.attribute}`, r);
  const rank = (a: string) => (FIRST_ATTRS.includes(a) ? FIRST_ATTRS.indexOf(a) : 9);
  return [...seen.values()]
    .sort((a, b) => rank(a.attribute) - rank(b.attribute) || a.entity.localeCompare(b.entity))
    .map((l, i) => ({ ...l, y: LANE_Y0 + i * LANE_GAP }));
}

function curve(a: [number, number], b: [number, number], n = 20): [number, number][] {
  const out: [number, number][] = [];
  const my = (a[1] + b[1]) / 2;
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const u = 1 - t;
    // Cubic Bezier with vertical tangents at both ends.
    const x = u * u * u * a[0] + 3 * u * u * t * a[0] + 3 * u * t * t * b[0] + t * t * t * b[0];
    const y = u * u * u * a[1] + 3 * u * u * t * my + 3 * u * t * t * my + t * t * t * b[1];
    out.push([x, y]);
  }
  return out;
}

const readX = (r: Read) => {
  // A whole month reads at its middle; a single day reads at that day.
  const end = r.to === null ? day("2025-01-01") : day(r.to);
  const mid = (day(r.from) + end) / 2;
  return dateX(new Date(mid * 86_400_000).toISOString().slice(0, 10));
};

export function layout(graph: Graph, change: Changeset | undefined) {
  const lanes = lanesOf(graph);
  const laneOf = new Map(lanes.map((l) => [`${l.entity}|${l.attribute}`, l]));
  const depth = change ? affectedBy(change, graph) : new Map<number, number>();
  const nodes: NodeSpec[] = graph.computations.map((c) => ({
    id: c.id,
    derivation: c.derivation,
    key: c.key,
    x: monthX(monthOf(c.key)),
    y: c.derivation === "payroll.gross" ? GROSS_Y : WH_Y,
    depth: depth.get(c.id) ?? null,
  }));
  const byId = new Map(nodes.map((n) => [n.id, n]));

  const edges: EdgeSpec[] = [];
  for (const c of graph.computations) {
    const n = byId.get(c.id)!;
    for (const r of c.reads) {
      const lane = laneOf.get(`${r.entity}|${r.attribute}`);
      if (!lane) continue;
      const hit = change?.changes.some((x) => x.entity === r.entity && x.attribute === r.attribute && overlaps(r, x));
      edges.push({
        points: curve([readX(r), lane.y], [n.x, n.y - NODE_R]),
        start: hit ? edgeStart(0) : -1,
        width: hit ? 2.4 : 1.2,
      });
    }
  }
  for (const e of graph.edges) {
    const a = byId.get(e.source);
    const b = byId.get(e.reader);
    if (!a || !b) continue;
    const d = b.depth;
    edges.push({
      points: curve([a.x, a.y + NODE_R], [b.x, b.y - NODE_R], 8),
      start: d !== null && d > 0 && a.depth !== null ? edgeStart(d) : -1,
      width: d !== null && d > 0 ? 2.4 : 1.2,
      dur: TIMING.derived,
    });
  }

  const changed: Changed[] = [];
  for (const x of change?.changes ?? []) {
    const lane = laneOf.get(`${x.entity}|${x.attribute}`);
    if (lane) changed.push({ lane, x0: dateX(x.from), x1: dateX(x.to) });
  }
  return { lanes, nodes, edges, changed, depth };
}

/** Thick polylines as triangles: position, distance along (0..1), side (-1..1), ink start. */
export function edgeBuffers(edges: EdgeSpec[]) {
  const pos: number[] = [];
  const along: number[] = [];
  const side: number[] = [];
  const start: number[] = [];
  const dur: number[] = [];
  const index: number[] = [];
  let base = 0;
  for (const e of edges) {
    const pts = e.points;
    const lens = [0];
    for (let i = 1; i < pts.length; i++) {
      lens.push(lens[i - 1]! + Math.hypot(pts[i]![0] - pts[i - 1]![0], pts[i]![1] - pts[i - 1]![1]));
    }
    const total = lens.at(-1) || 1;
    pts.forEach(([x, y], i) => {
      const [px, py] = pts[Math.max(0, i - 1)]!;
      const [nx, ny] = pts[Math.min(pts.length - 1, i + 1)]!;
      let dx = nx - px;
      let dy = ny - py;
      const l = Math.hypot(dx, dy) || 1;
      dx /= l;
      dy /= l;
      const hw = e.width / 2 + 0.75; // half width plus room for anti-aliasing
      for (const s of [-1, 1]) {
        pos.push(x - dy * hw * s, y + dx * hw * s, 0);
        along.push(lens[i]! / total);
        side.push(s);
        start.push(e.start);
        dur.push(e.dur ?? TIMING.edge);
      }
      if (i > 0) {
        const a = base + (i - 1) * 2;
        index.push(a, a + 1, a + 2, a + 1, a + 3, a + 2);
      }
    });
    base += pts.length * 2;
  }
  return {
    position: new Float32Array(pos),
    along: new Float32Array(along),
    side: new Float32Array(side),
    start: new Float32Array(start),
    dur: new Float32Array(dur),
    index,
  };
}
