"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useHydrated } from "@/lib/tokens";
import { fmtDate } from "@/lib/format";
import { cents } from "@/lib/payroll";
import { pieces, simulate } from "@/lib/simulate";
import { MONTHS } from "@/lib/scene";
import { signed } from "@/lib/story";
import type { WriteResult } from "@/lib/types";
import { PageHead } from "./PageHead";
import { useScene } from "./SceneProvider";

export function Payroll({ initialMonth = 3, initialSalary }: { initialMonth?: number; initialSalary?: number }) {
  const { scene, live, post, source } = useScene();
  const [month, setMonth] = useState(initialMonth);
  const [amount, setAmount] = useState(
    initialSalary ?? Math.round(((pieces(scene.salary.rows, scene.clock.version).at(-1)?.value ?? 0) + 500_000) / 100),
  );
  const [posting, setPosting] = useState(false);
  const [result, setResult] = useState<WriteResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Until hydration the button would submit the form natively and reload the page.
  const ready = useHydrated();

  const newCents = Math.round(amount * 100);
  const sim = useMemo(() => simulate(scene, month, newCents), [scene, month, newCents]);
  const { from, rows, checked, matches, grossDelta: totalDelta, whDelta } = sim;
  const currentSalary = sim.current?.value ?? 0;
  const changed = rows.filter((r) => r.after.gross_cents !== r.now);
  const writesOff = source.kind !== "live";
  // Outstanding work is counted across the tenant, so cap it at what this write caused.
  const outstanding = scene.clock.computations.stale + scene.clock.computations.pending;
  const left = result && !result.noop ? Math.min(outstanding, result.invalidated) : 0;
  const noChange = sim.noop;

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
          Currently {cents(currentSalary)} a year from {fmtDate(sim.current?.start ?? null)}.{" "}
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
                transaction.{" "}
                {left > 0 ? (
                  <>
                    Workers are recomputing them: {result.invalidated - left} of {result.invalidated} done.
                  </>
                ) : (
                  <>All {result.invalidated} are recomputed and the table below shows the new figures.</>
                )}
                <span className="progress" aria-hidden="true">
                  <span
                    style={{ width: `${(100 * (result.invalidated - left)) / Math.max(1, result.invalidated)}%` }}
                  />
                </span>
                <Link href="/invalidation">See which ones and why</Link>, or{" "}
                <Link href="/feed">read the corrections they published</Link>.
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
          {checked > 0 && (
            <>
              Check: the browser&rsquo;s arithmetic gives the backend&rsquo;s exact current gross for{" "}
              <strong className={matches === checked ? undefined : "red"}>
                {matches} of {checked}
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
                const now = r.now;
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
