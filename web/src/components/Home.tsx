"use client";

import Link from "next/link";
import { useState } from "react";
import { fmtDate } from "@/lib/format";
import { MONTHS } from "@/lib/scene";
import { signed, story } from "@/lib/story";
import { Bitemporal } from "./Bitemporal";
import { Ledger } from "./Ledger";
import { useScene } from "./SceneProvider";

const NAMES: Record<string, string> = { annual_salary_cents: "Salary", fte_bp: "FTE", state: "State" };

const CODE = `@derivation("payroll.gross", version="1")
def gross(ctx, key):
    entity, month = parse_key(key)
    salary = ctx.timeline(entity, "annual_salary_cents", month)
    fte = ctx.timeline(entity, "fte_bp", month)
    ...
    return {"gross_cents": cents, "days_paid": days}`;

const COLS = 200;
const ROWS = 24;
const HIT = 137;

/** The benchmark tenant as a grid: one column per employee, one row per month and derivation. */
function Field() {
  return (
    <svg
      className="field"
      viewBox={`0 0 ${COLS * 6} ${ROWS * 6}`}
      role="img"
      aria-label="4,800 results, 12 of them stale"
    >
      <defs>
        <pattern id="cell" width="6" height="6" patternUnits="userSpaceOnUse">
          <rect width="4.6" height="4.6" />
        </pattern>
      </defs>
      <rect className="field-all" width={COLS * 6} height={ROWS * 6} fill="url(#cell)" />
      {Array.from(
        { length: ROWS },
        (_, r) => r % 12 >= 6 && <rect key={r} className="field-hit" x={HIT * 6} y={r * 6} width="4.6" height="4.6" />,
      )}
    </svg>
  );
}

export function Home() {
  const { scene } = useScene();
  const versions = scene.clock.version;
  const [selected, setSelected] = useState(versions);
  const [shownLatest, setShownLatest] = useState(versions);
  if (shownLatest !== versions) {
    setShownLatest(versions);
    setSelected(versions);
  }
  const s = story(scene);

  return (
    <>
      <section className="hero-band">
        <Ledger />
        <ol className="hero-months" aria-hidden="true">
          {MONTHS.map((m) => (
            <li key={m}>{m}</li>
          ))}
        </ol>
        <div className="hero-inner">
          <h1 className="display">Fix a fact in the past. Recompute only what read it.</h1>
          <p className="lede">
            A Django library on Postgres for facts that change over time, like salaries and tax rates. Correct one
            retroactively and backdate recomputes just the results that depended on it, then hands you the differences.
          </p>
          <div className="actions">
            <Link className="button" href="/payroll">
              Backdate a raise
            </Link>
            <Link href="/invalidation">See what the last one touched</Link>
          </div>
        </div>
      </section>

      <div className="page home-page">
        <section className="block">
          <h2>What one correction does</h2>
          {s ? (
            <ol className="flow">
              <li>
                <Link href="/payroll">
                  <span className="flow-fig">{fmtDate(s.change.changes[0]?.from ?? null)}</span>
                  <span className="flow-t">
                    {NAMES[s.change.changes[0]?.attribute ?? ""] ?? "A fact"} corrected back to this date
                  </span>
                </Link>
              </li>
              <li>
                <Link href="/invalidation">
                  <span className="flow-fig">
                    {s.stale} <small>of {scene.computations.length}</small>
                  </span>
                  <span className="flow-t">results had read those dates, marked stale in the same transaction</span>
                </Link>
              </li>
              <li>
                <Link href="/workers">
                  <span className="flow-fig">{s.pending ? s.stale - s.pending : s.stale}</span>
                  <span className="flow-t">recomputed by workers, each under a lease</span>
                </Link>
              </li>
              <li>
                <Link href="/feed">
                  <span className="flow-fig red">{signed(s.grossDelta)}</span>
                  <span className="flow-t">gross pay difference, published to the correction feed</span>
                </Link>
              </li>
            </ol>
          ) : (
            <p>
              No correction yet. <Link href="/payroll">Backdate a raise</Link> to see one go through.
            </p>
          )}
        </section>

        <section className="block">
          <h2>12 results recomputed, not 4,800</h2>
          <Field />
          <p className="field-note">
            Each square is one result in the benchmark: 200 employees, 12 months, gross and withholding. One raise from
            1 July made the red ones stale. Fresh again in <strong>0.67 s</strong>, against <strong>8.82 s</strong> for
            recomputing everything. <Link href="/benchmarks">How it was measured</Link>
          </p>
        </section>

        <section className="block split code-split">
          <div>
            <h2>Write payroll as plain Python</h2>
            <p className="muted">
              Every fact a derivation reads through <code>ctx</code> is recorded with its dates. That record is how
              backdate knows what a correction touches.
            </p>
          </div>
          <pre className="code">{CODE}</pre>
        </section>

        <section className="block">
          <h2>Every version is kept</h2>
          <p className="muted">
            Employee {scene.employee}&rsquo;s salary as the database knew it after each write. Drag down or use the
            slider to read the past.
          </p>
          <div className="wide">
            <Bitemporal
              attribute="annual_salary_cents"
              rows={scene.salary.rows}
              versions={versions}
              selected={selected}
              onSelect={setSelected}
            />
          </div>
          <label className="scrub">
            <span>
              Reading at version <strong>{selected}</strong> of {versions}
            </span>
            <input
              type="range"
              min={1}
              max={versions}
              value={selected}
              onChange={(e) => setSelected(Number(e.target.value))}
              aria-label="Knowledge version"
            />
          </label>
        </section>
      </div>
    </>
  );
}
