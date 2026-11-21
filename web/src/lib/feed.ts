import type { Computation, Restatement } from "./types";

export const FIELD: Record<string, string> = {
  "payroll.gross": "gross_cents",
  "payroll.withholding": "withholding_cents",
};

const num = (r: Record<string, unknown> | number | null | undefined, k: string) => {
  const v = typeof r === "object" && r ? r[k] : undefined;
  return typeof v === "number" ? v : 0;
};

/** Feed lines for one derivation, as published up to and including version `upTo`, grouped by version. */
export function ledger(feed: Restatement[], derivation: string, upTo: number) {
  const field = FIELD[derivation]!;
  const lines = feed
    .filter((r) => r.computation.derivation === derivation && r.to_version <= upTo)
    .map((r) => ({
      r,
      previous: r.previous ? num(r.previous, field) : null,
      current: num(r.current, field),
      delta: num(r.delta, field),
    }));
  const groups = new Map<number, typeof lines>();
  for (const l of lines) groups.set(l.r.to_version, [...(groups.get(l.r.to_version) ?? []), l]);
  const balance = lines.reduce((s, l) => s + l.delta, 0);
  return { field, groups: [...groups.entries()].sort((a, b) => a[0] - b[0]), balance, count: lines.length };
}

/** What the stored results add up to now. Summed deltas must equal this at the latest version. */
export const stored = (comps: Computation[], derivation: string) =>
  comps.filter((c) => c.derivation === derivation).reduce((s, c) => s + num(c.result, FIELD[derivation]!), 0);
