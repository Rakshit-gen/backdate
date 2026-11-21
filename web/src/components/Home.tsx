"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { fmtDate, fmtTime, fmtValue } from "@/lib/format";
import { isCorrection, knownAt } from "@/lib/scene";
import { signed, story } from "@/lib/story";
import { Bitemporal } from "./Bitemporal";
import { useScene } from "./SceneProvider";

const NAMES: Record<string, string> = { annual_salary_cents: "Salary", fte_bp: "FTE", state: "State" };

export function Home() {
  const { scene } = useScene();
  const versions = scene.clock.version;
  const [selected, setSelected] = useState(versions);
  useEffect(() => setSelected(versions), [versions]);

  const lanes = useMemo(
    () => [
      { attribute: "annual_salary_cents", rows: scene.salary.rows },
      { attribute: "fte_bp", rows: scene.fte.rows },
      { attribute: "state", rows: scene.state.rows },
    ],
    [scene.salary, scene.fte, scene.state],
  );
  const change = scene.changesets.find((c) => c.version === selected);
  const s = story(scene);

  return (
    <div className="page">
      <div className="home-title">
        <h1 className="display">backdate</h1>
        <p className="lede">
          Bitemporal facts for Django on Postgres. Correct a salary back in March, and only the pay results that read
          March onwards are recomputed, under leases, with every change published as a correction you can post to a
          ledger.
        </p>
      </div>

      <section className="block">
        <h2>Employee {scene.employee}&rsquo;s salary, as the database knew it</h2>
        <p className="muted">
          Across: the dates a salary applies to. Down: each write, in order. A box is one stored row, kept forever.
          Hatched means a later write replaced it. Drag down the chart, or use the slider, to read the facts as they
          stood at any version.
        </p>
        <Bitemporal
          attribute="annual_salary_cents"
          rows={scene.salary.rows}
          versions={versions}
          selected={selected}
          onSelect={setSelected}
        />
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

        <div className="reading" aria-live="polite">
          <h3>
            Known at version {selected}{" "}
            <span className="muted">
              {change
                ? `after “${change.reason || "unnamed write"}” at ${fmtTime(change.recorded_at)}`
                : `(this write changed nothing for employee ${scene.employee})`}
            </span>
          </h3>
          <table>
            <thead>
              <tr>
                <th>Fact</th>
                <th>True from</th>
                <th>Until</th>
                <th className="num">Value</th>
                <th className="num">Written at</th>
              </tr>
            </thead>
            <tbody>
              {lanes.flatMap(({ attribute, rows }) =>
                knownAt(rows, selected).map((r) => (
                  <tr
                    key={`${attribute}${r.tx_from}${r.from}`}
                    className={isCorrection(rows, r, selected) ? "red" : undefined}
                  >
                    <td>{NAMES[attribute]}</td>
                    <td>{fmtDate(r.from)}</td>
                    <td>{r.to ? fmtDate(r.to) : "open"}</td>
                    <td className="num">{fmtValue(attribute, r.value)}</td>
                    <td className="num">v{r.tx_from}</td>
                  </tr>
                )),
              )}
              {knownAt(scene.salary.rows, selected).length === 0 && (
                <tr>
                  <td colSpan={5} className="muted">
                    Nothing yet. Employee {scene.employee} is hired at a later version.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="block">
        <h2>The last correction, start to finish</h2>
        {s ? (
          <ol className="steps">
            <li>
              <Link href="/payroll">
                <span className="step-n">1</span>
                <span className="step-t">Written</span>
                <span className="step-d">
                  Version {s.change.version}:{" "}
                  {s.change.changes
                    .map((c) => `${NAMES[c.attribute] ?? c.attribute} from ${fmtDate(c.from)}`)
                    .join(", ")}
                </span>
              </Link>
            </li>
            <li>
              <Link href="/invalidation">
                <span className="step-n">2</span>
                <span className="step-t">Marked stale</span>
                <span className="step-d">
                  {s.stale} of {scene.computations.length} results read the changed dates, in the same transaction
                </span>
              </Link>
            </li>
            <li>
              <Link href="/workers">
                <span className="step-n">3</span>
                <span className="step-t">Recomputed</span>
                <span className="step-d">
                  {s.pending ? `${s.pending} still waiting for a worker` : `all ${s.stale} recomputed under leases`}
                </span>
              </Link>
            </li>
            <li>
              <Link href="/feed">
                <span className="step-n">4</span>
                <span className="step-t">Published</span>
                <span className="step-d">
                  {s.restated.length} corrections in the feed: gross {signed(s.grossDelta)}, withholding{" "}
                  {signed(s.withholdingDelta)}
                </span>
              </Link>
            </li>
          </ol>
        ) : (
          <p>
            No correction yet, only the first entry. <Link href="/payroll">Backdate a raise</Link> to see one go
            through.
          </p>
        )}
      </section>
    </div>
  );
}
