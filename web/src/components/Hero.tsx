"use client";

import { motion, MotionConfig } from "motion/react";
import Link from "next/link";
import { useRef } from "react";
import { fmtDate } from "@/lib/format";
import { cents } from "@/lib/payroll";
import { MONTHS } from "@/lib/scene";
import type { simulate } from "@/lib/simulate";
import { signed } from "@/lib/story";

const W = 1000;
const H = 320;
const X0 = 16;
const SLOT = (W - 2 * X0) / 12;
const BAR = SLOT * 0.56;
const BASE = 262;
const TOP = 58;

type Sim = ReturnType<typeof simulate>;
type Props = {
  employee: number;
  sim: Sim;
  month: number;
  amount: number;
  onMonth: (m: number) => void;
  onAmount: (a: number) => void;
  total: number;
};

/** Drag the start of a raise across 2024 and watch which months of pay it rewrites. */
export function Hero({ employee, sim, month, amount, onMonth, onAmount, total }: Props) {
  const svg = useRef<SVGSVGElement>(null);
  const current = Math.round((sim.current?.value ?? 0) / 100);
  const max = Math.max(1, ...sim.rows.flatMap((r) => [r.now, r.after.gross_cents])) * 1.04;
  const h = (c: number) => ((BASE - TOP) * c) / max;
  const handleX = X0 + (month - 1) * SLOT;

  function drag(e: React.PointerEvent<SVGSVGElement>) {
    if (e.type === "pointermove" && !e.currentTarget.hasPointerCapture(e.pointerId)) return;
    if (e.type === "pointerdown") e.currentTarget.setPointerCapture(e.pointerId);
    const box = svg.current!.getBoundingClientRect();
    const x = ((e.clientX - box.left) / box.width) * W;
    onMonth(Math.min(12, Math.max(1, Math.round((x - X0) / SLOT) + 1)));
  }

  return (
    <MotionConfig reducedMotion="user" transition={{ type: "spring", stiffness: 260, damping: 30 }}>
      <div className="hero-tool">
        <div className="hero-controls">
          <label className="field">
            <span>
              Raise employee {employee} to <strong>{cents(amount * 100)}</strong> a year
            </span>
            <input
              type="range"
              min={Math.max(1000, current - 20_000)}
              max={current + 40_000}
              step={500}
              value={amount}
              onChange={(e) => onAmount(Number(e.target.value))}
            />
          </label>
          <label className="field">
            <span>
              starting <strong>{fmtDate(sim.from)}</strong>
            </span>
            <input
              type="range"
              min={1}
              max={12}
              step={1}
              value={month}
              onChange={(e) => onMonth(Number(e.target.value))}
            />
          </label>
        </div>

        <svg
          ref={svg}
          viewBox={`0 0 ${W} ${H}`}
          className="hero-chart"
          role="img"
          aria-label={`Monthly gross pay for 2024, ${sim.changed} months changed by the raise`}
          onPointerDown={drag}
          onPointerMove={drag}
        >
          <motion.rect
            className="hero-after"
            y={TOP - 34}
            height={BASE - TOP + 34}
            animate={{ x: handleX, width: W - X0 - handleX }}
            initial={false}
          />
          <line className="hero-base" x1={X0} x2={W - X0} y1={BASE} y2={BASE} />
          {sim.rows.map((r) => {
            const x = X0 + r.i * SLOT + (SLOT - BAR) / 2;
            const changed = r.after.gross_cents !== r.now;
            const after = h(r.after.gross_cents);
            const was = h(r.now);
            return (
              <g key={r.name} className={changed ? "m changed" : r.i + 1 < month ? "m before" : "m"}>
                <motion.rect x={x} width={BAR} initial={false} animate={{ y: BASE - after, height: after }} />
                {changed && (
                  <motion.line
                    className="was"
                    x1={x - 6}
                    x2={x + BAR + 6}
                    initial={false}
                    animate={{ y1: BASE - was, y2: BASE - was }}
                  />
                )}
                {changed && (
                  <text className="delta" x={x + BAR / 2} y={BASE - Math.max(after, was) - 10} textAnchor="middle">
                    {signed(r.after.gross_cents - r.now)}
                  </text>
                )}
                <text className="mlabel" x={x + BAR / 2} y={BASE + 24} textAnchor="middle">
                  {r.name}
                </text>
              </g>
            );
          })}
          <motion.g initial={false} animate={{ x: handleX }} className="hero-handle">
            <line x1={0} x2={0} y1={TOP - 40} y2={BASE + 8} />
            <rect x={-7} y={BASE + 36} width={14} height={22} rx={2} />
            <text x={8} y={TOP - 28}>
              from {fmtDate(sim.from)}
            </text>
          </motion.g>
        </svg>

        <p className="hero-result" aria-live="polite">
          {sim.noop ? (
            <>
              That is already the salary from {fmtDate(sim.from)} on, so nothing would change and no version would be
              spent.
            </>
          ) : (
            <>
              {sim.changed} {sim.changed === 1 ? "month" : "months"} of pay change, gross{" "}
              <span className="red">{signed(sim.grossDelta)}</span>. backdate would recompute{" "}
              <strong>
                {sim.stale} of {total}
              </strong>{" "}
              results and leave the rest alone.
            </>
          )}
        </p>
        <div className="actions">
          <Link className="button" href={`/payroll?from=${month}&salary=${amount}`}>
            {sim.noop ? "Open the payroll page" : "Post this raise"}
          </Link>
          <span className="muted small-inline">
            Worked out in your browser with the backend&rsquo;s arithmetic and its stored read sets.
          </span>
        </div>
      </div>
    </MotionConfig>
  );
}
