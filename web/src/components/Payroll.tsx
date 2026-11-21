"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useHydrated } from "@/lib/tokens";
import { fmtDate } from "@/lib/format";
import { assertFrom, cents, gross, type Piece, withholding } from "@/lib/payroll";
import { byDerivation, knownAt, MONTHS } from "@/lib/scene";
import { signed } from "@/lib/story";
import type { HistoryRow, WriteResult } from "@/lib/types";
import { PageHead } from "./PageHead";
import { useScene } from "./SceneProvider";

const pieces = (rows: HistoryRow[], v: number): Piece<number>[] =>
  knownAt(rows, v).map((r) => ({ start: r.from, end: r.to, value: r.value as number }));

const num = (r: Record<string, unknown> | null | undefined, k: string) =>
  typeof r?.[k] === "number" ? (r[k] as number) : null;

export function Payroll() {
  const { scene, live, post, source } = useScene();
  const v = scene.clock.version;
  const salaryNow = useMemo(() => pieces(scene.salary.rows, v), [scene.salary, v]);
  const fteNow = useMemo(() => pieces(scene.fte.rows, v), [scene.fte, v]);
  const currentSalary = salaryNow.at(-1)?.value ?? 0;

  const [month, setMonth] = useState(3);
  const [amount, setAmount] = useState(Math.round(currentSalary / 100) + 5000);
  const [posting, setPosting] = useState(false);
  const [result, setResult] = useState<WriteResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Until hydration the button would submit the form natively and reload the page.
  const ready = useHydrated();

  const from = `2024-${String(month).padStart(2, "0")}-01`;
  const newCents = Math.round(amount * 100);
  const salaryAfter = useMemo(() => assertFrom(salaryNow, from, newCents), [salaryNow, from, newCents]);

  const grossRes = byDerivation(scene.computations, "payroll.gross");
  const whRes = byDerivation(scene.computations, "payroll.withholding");

  const rows = MONTHS.map((name, i) => {
    const sim = gross(salaryNow, fteNow, 2024, i + 1);
    const after = gross(salaryAfter, fteNow, 2024, i + 1);
    const backend = num(grossRes[i]?.result, "gross_cents");
    const rate = num(whRes[i]?.result, "rate_bp") ?? 0;
    const whNow = num(whRes[i]?.result, "withholding_cents");
    const whAfter = withholding(after.gross_cents, rate);
    return { name, i, sim, after, backend, whNow, whAfter, stale: grossRes[i]?.status !== "fresh" };
  });

  const checked = rows.filter((r) => r.backend !== null && !r.stale);
  const matches = checked.filter((r) => r.backend === r.sim.gross_cents).length;
  const changed = rows.filter((r) => r.after.gross_cents !== (r.backend ?? r.sim.gross_cents));
  const totalDelta = rows.reduce((s, r) => s + r.after.gross_cents - (r.backend ?? r.sim.gross_cents), 0);
  const whDelta = rows.reduce((s, r) => s + r.whAfter - (r.whNow ?? 0), 0);
  const writesOff = source.kind !== "live";
  const noChange = newCents === currentSalary && salaryNow.at(-1)?.start === from;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setPosting(true);
    setError(null);
    try {
      setResult(await post(from, newCents));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPosting(false);
    }
  }

  return (
    <div className="page">
      <PageHead title="Payroll">
        <p>
          Give employee {scene.employee} a raise from any month of 2024 and see what it does to each month&rsquo;s pay.
          The new figures are worked out in your browser with the same arithmetic as the backend. Posting the correction
          writes it to the backend for real.
        </p>
      </PageHead>

      <form className="block correction" onSubmit={submit}>
        <h2>The correction</h2>
        <div className="fields">
          <label className="field">
            New annual salary
            <input
              type="number"
              min={0}
              max={1_000_000}
              step={100}
              value={amount}
              onChange={(e) => setAmount(Number(e.target.value))}
            />
          </label>
          <label className="field">
            Effective from
            <select value={month} onChange={(e) => setMonth(Number(e.target.value))}>
              {MONTHS.map((m, i) => (
                <option key={m} value={i + 1}>
                  1 {m} 2024
                </option>
              ))}
            </select>
          </label>
          <div className="field">
            <span>&nbsp;</span>
            <button type="submit" disabled={!ready || writesOff || posting || noChange || !(amount > 0)}>
              {posting ? "Posting…" : "Post correction"}
            </button>
          </div>
        </div>
        <p className="muted">
          Currently {cents(currentSalary)} a year from {fmtDate(salaryNow.at(-1)?.start ?? null)}.{" "}
          {writesOff
            ? "Posting needs the live backend; the table below still works."
            : "Posting writes one assert op through the page's proxy, which allows only this kind of write."}
        </p>
        {result && (
          <p className="notice" role="status">
            {result.noop ? (
              <>That salary was already true for those dates, so nothing changed and no version was spent.</>
            ) : (
              <>
                Posted as version {result.version}. The backend marked {result.invalidated} results stale in the same
                transaction. <Link href="/workers">Watch the workers recompute them</Link> or{" "}
                <Link href="/invalidation">see which ones and why</Link>.
              </>
            )}
          </p>
        )}
        {error && (
          <p className="notice error" role="alert">
            The backend refused the write: {error}
          </p>
        )}
      </form>

      <section className="block">
        <h2>Month by month</h2>
        <p className="muted">
          {checked.length > 0 && (
            <>
              Check: the browser&rsquo;s arithmetic gives the backend&rsquo;s exact current gross for{" "}
              <strong className={matches === checked.length ? undefined : "red"}>
                {matches} of {checked.length}
              </strong>{" "}
              months.{" "}
            </>
          )}
          This correction would change {changed.length} months: gross {signed(totalDelta)}, withholding{" "}
          {signed(whDelta)}.
        </p>
        <div className="table-wrap">
          <table className="months">
            <thead>
              <tr>
                <th>Month</th>
                <th className="num">Days paid</th>
                <th className="num">Gross now</th>
                <th className="num">Gross after</th>
                <th className="num">Change</th>
                <th className="num">Withholding now</th>
                <th className="num">After</th>
                <th className="num">Change</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const now = r.backend ?? r.sim.gross_cents;
                const d = r.after.gross_cents - now;
                const wd = r.whAfter - (r.whNow ?? 0);
                return (
                  <tr key={r.name} className={d === 0 && wd === 0 ? "before" : undefined}>
                    <td>
                      {r.name} 2024
                      {r.stale ? <span className="muted"> (recomputing)</span> : null}
                    </td>
                    <td className="num">{r.after.days_paid}</td>
                    <td className="num">{cents(now)}</td>
                    <td className="num strong">{cents(r.after.gross_cents)}</td>
                    <td className="num red">{d ? signed(d) : ""}</td>
                    <td className="num">{r.whNow === null ? "–" : cents(r.whNow)}</td>
                    <td className="num">{cents(r.whAfter)}</td>
                    <td className="num red">{wd ? signed(wd) : ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          &ldquo;Now&rdquo; columns are the backend&rsquo;s stored results. &ldquo;After&rdquo; columns are simulated:
          pay is salary &times; FTE &divide; 365 for each day employed, summed and rounded once, half to even (
          <code>examples/payroll/derivations.py</code>). Withholding uses the rate the backend last used for that month.
        </p>
      </section>
    </div>
  );
}
