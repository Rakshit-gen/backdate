"use client";

import { useEffect, useMemo, useState } from "react";
import { ledger, stored } from "@/lib/feed";
import { fmtTime } from "@/lib/format";
import { cents } from "@/lib/payroll";
import { MONTHS, monthOf } from "@/lib/scene";
import { signed } from "@/lib/story";
import { PageHead } from "./PageHead";
import { useScene } from "./SceneProvider";

const KINDS = [
  ["payroll.gross", "Gross pay"],
  ["payroll.withholding", "Withholding"],
] as const;

export function Feed() {
  const { scene } = useScene();
  const versions = useMemo(
    () => [...new Set(scene.restatements.map((r) => r.to_version))].sort((a, b) => a - b),
    [scene.restatements],
  );
  const latest = versions.at(-1) ?? 0;
  const [upTo, setUpTo] = useState(latest);
  const [kind, setKind] = useState<string>(KINDS[0][0]);
  useEffect(() => setUpTo(latest), [latest]);

  const { groups, balance, count } = ledger(scene.restatements, kind, upTo);
  const now = stored(scene.computations, kind);
  const reasons = new Map(scene.changesets.map((c) => [c.version, c.reason]));

  return (
    <div className="page">
      <PageHead title="Feed">
        <p>
          Every time a saved result actually changes, backdate appends a line to the correction feed: the old value, the
          new one and the difference. A ledger downstream only has to post the differences. Their running sum is always
          the current answer.
        </p>
      </PageHead>

      {versions.length === 0 ? (
        <section className="block">
          <p>The feed is empty: nothing for employee {scene.employee} has been computed yet.</p>
        </section>
      ) : (
        <>
          <section className="block feed-controls">
            <div className="buttons" role="group" aria-label="Result">
              {KINDS.map(([d, label]) => (
                <button key={d} type="button" className="plain" aria-pressed={kind === d} onClick={() => setKind(d)}>
                  {label}
                </button>
              ))}
            </div>
            <label className="scrub">
              Published up to version {upTo}
              <input
                type="range"
                min={0}
                max={versions.length - 1}
                step={1}
                value={Math.max(0, versions.indexOf(upTo))}
                onChange={(e) => setUpTo(versions[Number(e.target.value)]!)}
              />
            </label>
          </section>

          <section className="block balance">
            <p>
              {count} lines for employee {scene.employee}. Sum of the differences: <strong>{cents(balance)}</strong>.{" "}
              {upTo === latest ? (
                balance === now ? (
                  <>The stored results add up to the same {cents(now)}.</>
                ) : (
                  <span className="red">
                    The stored results add up to {cents(now)}, so a line is missing or still being published.
                  </span>
                )
              ) : (
                <>That is the year&rsquo;s total as a ledger reading the feed knew it at version {upTo}.</>
              )}
            </p>
          </section>

          {groups
            .slice()
            .reverse()
            .map(([v, lines]) => (
              <section key={v} className="block ledger">
                <h2>
                  Version {v}
                  <span className="muted">
                    {reasons.get(v) ? `, ${reasons.get(v)}` : ""}
                    {lines[0] ? `, published ${fmtTime(lines[0].r.created_at)}` : ""}
                  </span>
                </h2>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Month</th>
                        <th className="num">Was</th>
                        <th className="num">Now</th>
                        <th className="num">Difference</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...lines]
                        .sort((a, b) => monthOf(a.r.computation.key) - monthOf(b.r.computation.key))
                        .map((l) => (
                          <tr
                            key={`${l.r.computation.id}-${l.r.seq}`}
                            className={l.previous !== null ? "red" : undefined}
                          >
                            <td>{MONTHS[monthOf(l.r.computation.key)]} 2024</td>
                            <td className="num">
                              {l.previous === null ? (
                                <span className="muted">first result</span>
                              ) : (
                                <s>{cents(l.previous)}</s>
                              )}
                            </td>
                            <td className="num">{cents(l.current)}</td>
                            <td className="num">{signed(l.delta)}</td>
                          </tr>
                        ))}
                    </tbody>
                    <tfoot>
                      <tr>
                        <td>Version total</td>
                        <td />
                        <td />
                        <td className="num strong">{signed(lines.reduce((s, l) => s + l.delta, 0))}</td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </section>
            ))}
        </>
      )}
    </div>
  );
}
