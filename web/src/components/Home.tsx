"use client";

import Link from "next/link";
import { useState } from "react";
import { fmtDate } from "@/lib/format";
import { signed, story } from "@/lib/story";
import { Bars } from "./Bars";
import { Bitemporal } from "./Bitemporal";
import { Ledger } from "./Ledger";
import { useScene } from "./SceneProvider";

const NAMES: Record<string, string> = { annual_salary_cents: "Salary", fte_bp: "FTE", state: "State" };

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
          <h2>What happens when you correct a fact</h2>
          <p className="muted">Shown with the last real correction in this demo.</p>
          {s ? (
            <ol className="steps">
              <li>
                <Link href="/payroll">
                  <span className="step-n">1</span>
                  <span className="step-t">You correct a fact</span>
                  <span className="step-d">
                    {s.change.changes
                      .map((c) => `${NAMES[c.attribute] ?? c.attribute} from ${fmtDate(c.from)}`)
                      .join(", ")}
                  </span>
                </Link>
              </li>
              <li>
                <Link href="/invalidation">
                  <span className="step-n">2</span>
                  <span className="step-t">It finds what read it</span>
                  <span className="step-d">
                    {s.stale} of {scene.computations.length} results, in the same transaction
                  </span>
                </Link>
              </li>
              <li>
                <Link href="/workers">
                  <span className="step-n">3</span>
                  <span className="step-t">Workers recompute</span>
                  <span className="step-d">
                    {s.pending ? `${s.pending} still waiting` : `All ${s.stale}, each under a lease`}
                  </span>
                </Link>
              </li>
              <li>
                <Link href="/feed">
                  <span className="step-n">4</span>
                  <span className="step-t">You get the differences</span>
                  <span className="step-d">
                    Gross {signed(s.grossDelta)}, withholding {signed(s.withholdingDelta)}
                  </span>
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

        <section className="block split">
          <div>
            <h2>12 results recomputed, not 4,800</h2>
            <p className="muted">One backdated raise across 200 employees.</p>
            <Link href="/benchmarks">How this was measured</Link>
          </div>
          <div>
            <Bars
              caption="Results recomputed"
              rows={[
                { label: "backdate", value: 12, shown: "12", accent: true },
                { label: "Everything", value: 4800, shown: "4,800" },
              ]}
            />
            <Bars
              caption="Time until every result is fresh"
              rows={[
                { label: "backdate", value: 0.67, shown: "0.67 s", accent: true },
                { label: "Everything", value: 8.82, shown: "8.82 s" },
              ]}
            />
          </div>
        </section>
      </div>
    </>
  );
}
