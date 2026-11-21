"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ATTRIBUTE_NAMES, fmtDate, fmtTime } from "@/lib/format";
import { cents } from "@/lib/payroll";
import { affectedBy, MONTHS, monthOf } from "@/lib/scene";
import { Loom } from "./Loom";
import { PageHead } from "./PageHead";
import { useScene } from "./SceneProvider";

const short = (d: string) => (d === "payroll.gross" ? "Gross" : d === "payroll.withholding" ? "Withholding" : d);
const span = (from: string, to: string | null) =>
  to && new Date(Date.parse(to) - 86_400_000).toISOString().slice(0, 10) === from
    ? fmtDate(from)
    : `${fmtDate(from)} to ${to ? fmtDate(to) : "open"}`;

export function Invalidation() {
  const { scene, lastWrite } = useScene();
  const corrections = useMemo(() => scene.changesets.slice(1), [scene.changesets]);
  const [version, setVersion] = useState<number | null>(corrections.at(-1)?.version ?? null);
  const [picked, setPicked] = useState<number | null>(null);
  const [replay, setReplay] = useState(0);

  // A new correction posted from this browser becomes the one shown.
  const latest = corrections.at(-1)?.version ?? null;
  useEffect(() => setVersion(latest), [latest]);

  const change = corrections.find((c) => c.version === version);
  const depth = useMemo(
    () => (change ? affectedBy(change, scene.graph) : new Map<number, number>()),
    [change, scene.graph],
  );
  const stale = scene.graph.computations
    .filter((c) => depth.has(c.id))
    .sort((a, b) => monthOf(a.key) - monthOf(b.key) || a.derivation.localeCompare(b.derivation));
  const node = scene.graph.computations.find((c) => c.id === picked);
  const reported = lastWrite && lastWrite.version === version ? lastWrite.invalidated : null;

  return (
    <div className="page">
      <PageHead title="Invalidation">
        <p>
          Every result remembers which date ranges of which facts it read. A write that changes a range marks exactly
          the results that read it as stale, plus whatever read those, in the same transaction. Here is that join, drawn
          from the read sets the backend stored.
        </p>
      </PageHead>

      {corrections.length === 0 ? (
        <section className="block">
          <p>
            Nothing has been corrected yet: there is only the first entry for employee {scene.employee}.{" "}
            <Link href="/payroll">Backdate a raise</Link> and come back.
          </p>
        </section>
      ) : (
        <>
          <section className="block">
            <div className="toolbar">
              <div className="buttons" role="group" aria-label="Correction">
                {corrections.map((c) => (
                  <button
                    key={c.version}
                    type="button"
                    className="plain"
                    aria-pressed={c.version === version}
                    onClick={() => setVersion(c.version)}
                  >
                    v{c.version}:{" "}
                    {c.changes
                      .map((x) => `${ATTRIBUTE_NAMES[x.attribute] ?? x.attribute} from ${fmtDate(x.from)}`)
                      .join(", ")}
                  </button>
                ))}
              </div>
              <button type="button" className="plain" onClick={() => setReplay((n) => n + 1)}>
                Replay
              </button>
            </div>
            <div className="wide">
              <Loom graph={scene.graph} change={change} picked={picked} onPick={setPicked} replay={replay} />
            </div>
            <p className="muted small">
              Top: the facts, January to December, with the changed range in red. Lines are recorded reads: a gross
              result reads its month of salary and FTE, a withholding result reads the state and its tax rate on the
              month&rsquo;s last day, plus that month&rsquo;s gross. Click a result to see its read set. Drawn from
              today&rsquo;s read sets.
            </p>
          </section>

          <section className="block split">
            <div>
              <h2>
                {stale.length} of {scene.graph.computations.length} results marked stale
              </h2>
              <p className="muted">
                {change && (
                  <>
                    Version {change.version}, written at {fmtTime(change.recorded_at)}.{" "}
                  </>
                )}
                {reported !== null && (
                  <>
                    The backend&rsquo;s own count for this write was <strong>{reported}</strong>
                    {reported === stale.length ? ", the same." : ". The difference means read sets moved since."}
                  </>
                )}
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Month</th>
                      <th>Gross</th>
                      <th>Withholding</th>
                    </tr>
                  </thead>
                  <tbody>
                    {MONTHS.map((m, i) => {
                      const cell = (d: string) => {
                        const c = stale.find((x) => x.derivation === d && monthOf(x.key) === i);
                        if (!c) return <td className="muted">untouched</td>;
                        return (
                          <td className={c.id === picked ? "picked" : undefined}>
                            <button type="button" className="link" onClick={() => setPicked(c.id)}>
                              {depth.get(c.id) === 0 ? "read the changed dates" : "read a stale gross"}
                            </button>
                          </td>
                        );
                      };
                      return (
                        <tr key={m}>
                          <td>{m}</td>
                          {cell("payroll.gross")}
                          {cell("payroll.withholding")}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="detail" aria-live="polite">
              {node ? (
                <>
                  <h2>
                    {short(node.derivation)}, {MONTHS[monthOf(node.key)]} 2024
                  </h2>
                  <p className="muted">
                    <code>{node.derivation}</code> key <code>{node.key}</code>, status {node.status}, computed at
                    version {node.result_version ?? "–"}, result seq {node.result_seq}.
                  </p>
                  <table>
                    <thead>
                      <tr>
                        <th>Read</th>
                        <th>Dates</th>
                      </tr>
                    </thead>
                    <tbody>
                      {node.reads.map((r) => (
                        <tr key={`${r.entity}${r.attribute}${r.from}`}>
                          <td>
                            {ATTRIBUTE_NAMES[r.attribute] ?? r.attribute}
                            <span className="muted"> {r.entity}</span>
                          </td>
                          <td>{span(r.from, r.to)}</td>
                        </tr>
                      ))}
                      {scene.graph.edges
                        .filter((e) => e.reader === node.id)
                        .map((e) => (
                          <tr key={e.source}>
                            <td>Gross result</td>
                            <td>seq {e.observed_seq}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                  {node.result && (
                    <p className="small">
                      Result:{" "}
                      {Object.entries(node.result)
                        .map(([k, v]) =>
                          typeof v !== "number"
                            ? `${k} ${String(v)}`
                            : k.endsWith("_cents")
                              ? `${k.replace(/_cents$/, "").replace("_", " ")} ${cents(v)}`
                              : k === "rate_bp"
                                ? `rate ${(v / 100).toFixed(2)}%`
                                : `${k.replace("_", " ")} ${v}`,
                        )
                        .join(", ")}
                    </p>
                  )}
                </>
              ) : (
                <p className="muted">Click a result in the graph or the table to see exactly what it read.</p>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
