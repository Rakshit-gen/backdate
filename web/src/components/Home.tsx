"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { fmtDate, fmtTime, fmtValue } from "@/lib/format";
import { isCorrection, knownAt, MONTHS } from "@/lib/scene";
import { pieces, simulate } from "@/lib/simulate";
import { signed, story } from "@/lib/story";
import { Bars } from "./Bars";
import { Bitemporal } from "./Bitemporal";
import { Hero } from "./Hero";
import { useScene } from "./SceneProvider";

const NAMES: Record<string, string> = { annual_salary_cents: "Salary", fte_bp: "FTE", state: "State" };

const readSpan = (from: string, to: string | null) => {
  const last = to ? new Date(Date.parse(to) - 86_400_000).toISOString().slice(0, 10) : null;
  return last === from ? fmtDate(from) : `${fmtDate(from)} to ${last ? fmtDate(last) : "open"}`;
};

const CODE = `@derivation("payroll.gross", version="1")
def gross(ctx, key):
    entity, month = parse_key(key)        # "7:2024-06"
    salary = ctx.timeline(entity, "annual_salary_cents", month)
    fte = ctx.timeline(entity, "fte_bp", month)
    ...  # prorate by day, round once, half to even
    return {"gross_cents": cents, "days_paid": days_paid}


@derivation("payroll.withholding", version="1")
def withholding(ctx, key):
    entity, month = parse_key(key)
    gross = ctx.derived("payroll.gross", key)
    state = ctx.value_at(entity, "state", last_day)
    rate = ctx.value_at(f"taxrate:{state}", "withholding_bp", last_day)
    ...`;

export function Home() {
  const { scene } = useScene();
  const versions = scene.clock.version;
  const [selected, setSelected] = useState(versions);
  const [shownLatest, setShownLatest] = useState(versions);
  if (shownLatest !== versions) {
    setShownLatest(versions);
    setSelected(versions);
  }

  const lanes = useMemo(
    () => [
      { attribute: "annual_salary_cents", rows: scene.salary.rows },
      { attribute: "fte_bp", rows: scene.fte.rows },
      { attribute: "state", rows: scene.state.rows },
    ],
    [scene.salary, scene.fte, scene.state],
  );
  const change = scene.changesets.find((c) => c.version === selected);

  const [month, setMonth] = useState(6);
  const [amount, setAmount] = useState(
    () => Math.round((pieces(scene.salary.rows, versions).at(-1)?.value ?? 0) / 100) + 5000,
  );
  const sim = useMemo(() => simulate(scene, month, amount * 100), [scene, month, amount]);
  const key = `${scene.employee}:2024-${String(month).padStart(2, "0")}`;
  const ran = scene.graph.computations.filter((c) => c.key === key);
  const s = story(scene);

  return (
    <div className="page">
      <section className="hero">
        <div className="hero-head">
          <h1 className="display">Fix a fact in the past. Recompute only what read it.</h1>
          <p className="lede">
            backdate keeps every version of every fact in Postgres. When a salary is corrected back to March, it knows
            exactly which pay results read March onwards, recomputes those on workers, and publishes each change as a
            correction a ledger can post.
          </p>
        </div>
        <Hero
          employee={scene.employee}
          sim={sim}
          month={month}
          amount={amount}
          onMonth={setMonth}
          onAmount={setAmount}
          total={scene.computations.length}
        />
      </section>

      <section className="block">
        <h2>What happened to the last real correction</h2>
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

      <section className="block">
        <h2>Nothing is overwritten</h2>
        <p className="muted">
          Employee {scene.employee}&rsquo;s salary, as the database knew it after each write. Across: the dates a salary
          applies to. Down: each write, in order. A box is one stored row, kept forever. Hatched means a later write
          replaced it. Drag down the chart, or use the slider, to read the facts as they stood at any version.
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

        <div className="reading" aria-live="polite">
          <h3>
            Known at version {selected}{" "}
            <span className="muted">
              {change
                ? `after “${change.reason || "unnamed write"}” at ${fmtTime(change.recorded_at)}`
                : `(this write changed nothing for employee ${scene.employee})`}
            </span>
          </h3>
          <div className="table-wrap">
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
        </div>
      </section>

      <section className="block split code-split">
        <div>
          <h2>You write plain Python</h2>
          <p className="muted">
            A derivation reads facts through <code>ctx</code>. That is how backdate learns which dates of which facts
            each result depends on. This is the real one from <code>examples/payroll/derivations.py</code>, trimmed.
          </p>
          <pre className="code">{CODE}</pre>
        </div>
        <div>
          <h2>backdate records what it read</h2>
          <p className="muted">
            The read sets stored for employee {scene.employee} in {MONTHS[month - 1]} 2024, the month picked above.
            These rows are what a correction is joined against.
          </p>
          {ran.map((c) => (
            <div key={c.id} className="table-wrap reads">
              <table>
                <caption>
                  <code>{c.derivation}</code> for {MONTHS[month - 1]}
                </caption>
                <tbody>
                  {c.reads.map((r) => (
                    <tr key={`${r.entity}${r.attribute}${r.from}`}>
                      <td>{NAMES[r.attribute] ?? (r.attribute === "withholding_bp" ? "Tax rate" : r.attribute)}</td>
                      <td>{readSpan(r.from, r.to)}</td>
                    </tr>
                  ))}
                  {scene.graph.edges
                    .filter((e) => e.reader === c.id)
                    .map((e) => (
                      <tr key={e.source}>
                        <td>Gross result</td>
                        <td>the same month</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      </section>

      <section className="block split">
        <div>
          <h2>Twelve results, not every result</h2>
          <p className="muted">
            In the benchmark, one raise for one of 200 employees, effective 1 July. Recomputing everything is what you
            do without read sets.
          </p>
          <Link href="/benchmarks">All the numbers and how they were measured</Link>
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
  );
}
