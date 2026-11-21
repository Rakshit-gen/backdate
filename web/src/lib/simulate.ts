// What a backdated raise would do, worked out in the browser with the backend's own arithmetic
// and the backend's stored read sets. Shared by the home page and the payroll page.
import { assertFrom, gross, type Piece, withholding } from "./payroll";
import { affectedBy, byDerivation, knownAt, MONTHS } from "./scene";
import type { HistoryRow, Scene, Span } from "./types";

export const pieces = (rows: HistoryRow[], v: number): Piece<number>[] =>
  knownAt(rows, v).map((r) => ({ start: r.from, end: r.to, value: r.value as number }));

const num = (r: Record<string, unknown> | null | undefined, k: string) =>
  typeof r?.[k] === "number" ? (r[k] as number) : null;

const before = (a: string | null, b: string | null) => (a === null ? false : b === null ? true : a < b);

/**
 * The date ranges an assert of `value` from `from` onwards would really change: everything from
 * `from` on, minus the stretches where the salary already had that value. Like the backend's diff.
 */
export function changedSpans(current: Piece<number>[], from: string, value: number): Span[] {
  let spans: Span[] = [{ from, to: null }];
  for (const p of current) {
    if (p.value !== value) continue;
    spans = spans.flatMap((s) => {
      // Cut [p.start, p.end) out of s.
      if (!before(s.from, p.end) || !before(p.start, s.to)) return [s];
      const out: Span[] = [];
      if (s.from < p.start) out.push({ from: s.from, to: p.start });
      if (p.end !== null && before(p.end, s.to)) out.push({ from: p.end, to: s.to });
      return out;
    });
  }
  return spans;
}

export function simulate(scene: Scene, month: number, newCents: number) {
  const v = scene.clock.version;
  const salaryNow = pieces(scene.salary.rows, v);
  const fteNow = pieces(scene.fte.rows, v);
  const from = `2024-${String(month).padStart(2, "0")}-01`;
  const salaryAfter = assertFrom(salaryNow, from, newCents);
  const grossRes = byDerivation(scene.computations, "payroll.gross");
  const whRes = byDerivation(scene.computations, "payroll.withholding");

  const rows = MONTHS.map((name, i) => {
    const sim = gross(salaryNow, fteNow, 2024, i + 1);
    const after = gross(salaryAfter, fteNow, 2024, i + 1);
    const backend = num(grossRes[i]?.result, "gross_cents");
    const rate = num(whRes[i]?.result, "rate_bp") ?? 0;
    const whNow = num(whRes[i]?.result, "withholding_cents");
    const now = backend ?? sim.gross_cents;
    return {
      name,
      i,
      sim,
      after,
      backend,
      now,
      whNow,
      whAfter: withholding(after.gross_cents, rate),
      stale: grossRes[i]?.status !== "fresh",
    };
  });

  const spans = changedSpans(salaryNow, from, newCents);
  const stale = spans.length
    ? affectedBy(
        {
          version: v + 1,
          recorded_at: "",
          actor: "",
          reason: "",
          changes: spans.map((s) => ({ ...s, entity: `employee:${scene.employee}`, attribute: "annual_salary_cents" })),
        },
        scene.graph,
      ).size
    : 0;

  const checked = rows.filter((r) => r.backend !== null && !r.stale);
  return {
    from,
    rows,
    current: salaryNow.at(-1),
    stale,
    noop: spans.length === 0,
    matches: checked.filter((r) => r.backend === r.sim.gross_cents).length,
    checked: checked.length,
    changed: rows.filter((r) => r.after.gross_cents !== r.now).length,
    grossDelta: rows.reduce((s, r) => s + r.after.gross_cents - r.now, 0),
    whDelta: rows.reduce((s, r) => s + r.whAfter - (r.whNow ?? 0), 0),
  };
}
