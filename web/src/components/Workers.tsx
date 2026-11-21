"use client";

import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { cents } from "@/lib/payroll";
import { byDerivation, MONTHS } from "@/lib/scene";
import type { Computation } from "@/lib/types";
import { PageHead } from "./PageHead";
import { useScene } from "./SceneProvider";

const ROWS = [
  ["payroll.gross", "Gross", "gross_cents"],
  ["payroll.withholding", "Withholding", "withholding_cents"],
] as const;

const leased = (c: Computation) => c.lease.expires_at !== null && Date.parse(c.lease.expires_at) > Date.now();

function Cell({ c, field }: { c: Computation | undefined; field: string }) {
  const reduced = useReducedMotion();
  // Flash only when a cell changes after the page loaded, not on first paint.
  const seen = useRef(false);
  useEffect(() => {
    seen.current = true;
  }, []);
  if (!c) return <td className="muted">none</td>;
  const value = c.result?.[field];
  const busy = c.status !== "fresh";
  return (
    <td className={`job ${c.status}`}>
      <motion.div
        key={`${c.status}-${c.result_seq}`}
        initial={
          reduced || !seen.current ? false : { backgroundColor: busy ? "var(--flash-red)" : "var(--flash-blue)" }
        }
        animate={{ backgroundColor: "rgba(0,0,0,0)" }}
        transition={{ duration: 0.9 }}
        className="job-in"
      >
        <span className="job-v">{typeof value === "number" ? cents(value) : "–"}</span>
        <span className="job-s">
          {c.status}
          {leased(c) ? `, held by ${c.lease.owner}` : ""}
        </span>
        <span className="job-m">
          seq {c.result_seq}, token {c.lease.token}
          {c.attempts > 0 ? `, attempt ${c.attempts}` : ""}
        </span>
      </motion.div>
    </td>
  );
}

const STEPS: { title: string; body: string; slow: string; fast: string; row: [string, string, string] }[] = [
  {
    title: "The slow worker claims the job",
    body: "Claiming bumps the lease token and sets an expiry. The slow worker reads its facts and starts computing.",
    slow: "holds token 1, computing",
    fast: "idle",
    row: ["slow", "1", "in 30 s"],
  },
  {
    title: "Its lease runs out",
    body: "It stalls: a long GC pause, a lost network, a laptop lid. Nothing tells it that time has passed. The test forces this by setting the expiry in the past.",
    slow: "still thinks it holds token 1",
    fast: "idle",
    row: ["slow", "1", "expired"],
  },
  {
    title: "The fast worker claims the same job",
    body: "Expired leases are claimable. The same UPDATE bumps the token again, so the new holder has a number the old one can never have.",
    slow: "still thinks it holds token 1",
    fast: "holds token 2, computing",
    row: ["fast", "2", "in 30 s"],
  },
  {
    title: "The fast worker saves",
    body: "The save locks the row and checks the token it was given against the row's token. 2 equals 2, so the result is written and the lease is cleared. The token stays at 2.",
    slow: "still thinks it holds token 1",
    fast: "saved",
    row: ["none", "2", "cleared"],
  },
  {
    title: "The slow worker tries to save and is fenced off",
    body: "It wakes up and tries to write its own, older answer. 1 is not 2, so save returns FENCED and writes nothing. The fast worker's result stays.",
    slow: "FENCED, nothing written",
    fast: "saved",
    row: ["none", "2", "cleared"],
  },
];

export function Workers() {
  const { scene, live, busy } = useScene();
  const [step, setStep] = useState(0);
  const counts = scene.clock.computations;
  const s = STEPS[step]!;

  return (
    <div className="page">
      <PageHead title="Workers">
        <p>
          Workers claim stale results with <code>FOR UPDATE SKIP LOCKED</code>, recompute them and save them. Each claim
          is a lease with a fencing token, so a worker that stalls past its lease can never overwrite the one that took
          over.
        </p>
      </PageHead>

      <section className="block">
        <h2>Employee {scene.employee}&rsquo;s results</h2>
        <p className="muted">
          {live
            ? busy
              ? "Watching the backend while the workers catch up."
              : "Live from the backend."
            : "From the recording."}{" "}
          Across the tenant: {counts.fresh} fresh, {counts.stale} stale, {counts.pending} pending, {counts.failed}{" "}
          failed.{" "}
          {!busy && (
            <>
              <Link href="/payroll">Post a correction</Link> to watch them recompute.
            </>
          )}
        </p>
        <div className="table-wrap">
          <table className="jobs">
            <thead>
              <tr>
                <th>Month</th>
                {ROWS.map(([d, label]) => (
                  <th key={d}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {MONTHS.map((m, i) => (
                <tr key={m}>
                  <th scope="row">{m} 2024</th>
                  {ROWS.map(([d, , field]) => (
                    <Cell key={d} c={byDerivation(scene.computations, d)[i]} field={field} />
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted small">
          Seq counts how many times the stored value actually changed. Token counts claims, so it goes up even when a
          recompute lands on the same value.
        </p>
      </section>

      <section className="block">
        <h2>Fencing, step by step</h2>
        <p className="muted">
          A replay of <code>tests/test_races.py::test_expired_lease_is_fenced_off</code>, not live data. The test drives
          two workers by hand so the race happens the same way every run.
        </p>
        <div className="fence">
          <ol className="fence-steps">
            {STEPS.map((x, i) => (
              <li key={x.title}>
                <button type="button" className="plain" aria-pressed={i === step} onClick={() => setStep(i)}>
                  {i + 1}. {x.title}
                </button>
              </li>
            ))}
          </ol>
          <div className="fence-view" aria-live="polite">
            <h3>{s.title}</h3>
            <p>{s.body}</p>
            <table>
              <tbody>
                <tr>
                  <th scope="row">Row: lease owner, token, expiry</th>
                  <td>{s.row.join(", ")}</td>
                </tr>
                <tr>
                  <th scope="row">Slow worker</th>
                  <td className={step === 4 ? "red strong" : undefined}>{s.slow}</td>
                </tr>
                <tr>
                  <th scope="row">Fast worker</th>
                  <td>{s.fast}</td>
                </tr>
              </tbody>
            </table>
            <div className="buttons">
              <button type="button" className="plain" disabled={step === 0} onClick={() => setStep(step - 1)}>
                Back
              </button>
              <button type="button" disabled={step === STEPS.length - 1} onClick={() => setStep(step + 1)}>
                Next step
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
