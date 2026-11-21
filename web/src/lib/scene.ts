// Pure helpers over a Scene. The overlap rule is the one the backend's invalidation SQL uses.
import type { Changeset, Computation, Graph, HistoryRow, Span } from "./types";

const DAY = 86_400_000;
export const day = (iso: string) => Date.parse(`${iso}T00:00:00Z`) / DAY;

export const YEAR = { from: "2024-01-01", to: "2025-01-01" } as const;
export const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Position of a date across 2024, 0 at 1 January, 1 at the following 1 January. */
export function yearFraction(iso: string | null): number {
  const t = iso === null ? day(YEAR.to) : day(iso);
  return Math.min(1, Math.max(0, (t - day(YEAR.from)) / (day(YEAR.to) - day(YEAR.from))));
}

/** Half-open daterange overlap, open end meaning infinity. Same as Postgres `&&`. */
export function overlaps(a: Span, b: Span): boolean {
  const aEnd = a.to === null ? Infinity : day(a.to);
  const bEnd = b.to === null ? Infinity : day(b.to);
  return day(a.from) < bEnd && day(b.from) < aEnd;
}

/** Rows believed at knowledge version v. */
export function knownAt(rows: HistoryRow[], v: number): HistoryRow[] {
  return rows.filter((r) => r.tx_from <= v && (r.tx_to === null || r.tx_to > v));
}

export function monthOf(key: string): number {
  return Number(key.split("-").at(-1)) - 1;
}

/**
 * Computations a changeset would mark stale: those whose reads overlap a change, then
 * everything that read those, transitively. Returns id -> depth (0 = read the fact directly).
 */
export function affectedBy(change: Changeset, graph: Graph): Map<number, number> {
  const depth = new Map<number, number>();
  for (const c of graph.computations) {
    const hit = c.reads.some((r) =>
      change.changes.some((x) => x.entity === r.entity && x.attribute === r.attribute && overlaps(r, x)),
    );
    if (hit) depth.set(c.id, 0);
  }
  let frontier = [...depth.keys()];
  while (frontier.length) {
    const next: number[] = [];
    for (const e of graph.edges) {
      if (frontier.includes(e.source) && !depth.has(e.reader)) {
        depth.set(e.reader, (depth.get(e.source) ?? 0) + 1);
        next.push(e.reader);
      }
    }
    frontier = next;
  }
  return depth;
}

export function byDerivation(comps: Computation[], name: string): (Computation | undefined)[] {
  const out: (Computation | undefined)[] = Array(12).fill(undefined);
  for (const c of comps) if (c.derivation === name) out[monthOf(c.key)] = c;
  return out;
}

/** A row first written at v, replacing something already known: a correction. */
/**
 * A row written at version v corrects the past if, for some of its dates, the previous version
 * believed a different value. The untouched piece left over when a write splits a row is not one.
 */
export function isCorrection(rows: HistoryRow[], row: HistoryRow, v: number): boolean {
  if (row.tx_from !== v) return false;
  return knownAt(rows, v - 1).some(
    (old) => overlaps(old, row) && JSON.stringify(old.value) !== JSON.stringify(row.value),
  );
}
