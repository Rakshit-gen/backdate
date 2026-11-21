"use client";

import { useEffect, useMemo, useState } from "react";
import { fmtDate, fmtTime, fmtValue } from "@/lib/format";
import { isCorrection, knownAt } from "@/lib/scene";
import { SheetStack, type Lane } from "./SheetStack";
import { useScene } from "./SceneProvider";

export function Hero() {
  const { scene } = useScene();
  const versions = scene.clock.version;
  const [selected, setSelected] = useState(versions);
  const lanes: Lane[] = useMemo(
    () => [
      { attribute: "annual_salary_cents", rows: scene.salary.rows },
      { attribute: "fte_bp", rows: scene.fte.rows },
      { attribute: "state", rows: scene.state.rows },
    ],
    [scene.salary, scene.fte, scene.state],
  );

  // A new version arriving from a write moves the view to it.
  useEffect(() => setSelected(versions), [versions]);

  const change = scene.changesets.find((c) => c.version === selected);

  return (
    <header className="hero">
      <div className="hero-title">
        <h1>backdate</h1>
        <p className="lede">
          Bitemporal facts for Django on Postgres. Correct a salary back in March, and only the pay
          results that read March onwards are recomputed, under leases, with every change published
          as a correction you can post to a ledger.
        </p>
      </div>

      <figure className="hero-figure">
        <SheetStack lanes={lanes} versions={versions} selected={selected} />
        <figcaption>
          <label className="scrub">
            <span>
              Knowledge version <strong className="carbon">{selected}</strong> of {versions}
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
          <p className="muted">
            Each sheet is what the database believed about employee {scene.employee} after one more
            write. Left to right is the date a value is true for. Drag back to see what was known
            before a correction.
          </p>
        </figcaption>
      </figure>

      <div className="reading" aria-live="polite">
        <h3>
          Known at version {selected}
          {change ? (
            <span className="muted"> after &ldquo;{change.reason || "unnamed write"}&rdquo;, {fmtTime(change.recorded_at)}</span>
          ) : (
            <span className="muted"> (this version changed nothing for employee {scene.employee})</span>
          )}
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
                <tr key={`${attribute}${r.tx_from}${r.from}`} className={isCorrection(rows, r, selected) ? "red" : undefined}>
                  <td>{attribute === "annual_salary_cents" ? "Salary" : attribute === "fte_bp" ? "FTE" : "State"}</td>
                  <td>{fmtDate(r.from)}</td>
                  <td>{r.to ? fmtDate(r.to) : "open"}</td>
                  <td className="num">{fmtValue(attribute, r.value)}</td>
                  <td className="num">v{r.tx_from}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
        {knownAt(scene.salary.rows, selected).length === 0 && (
          <p className="muted">Nothing yet: employee {scene.employee} is hired at a later version.</p>
        )}
      </div>
    </header>
  );
}
