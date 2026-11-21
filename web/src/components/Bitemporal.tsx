"use client";

import { useRef } from "react";
import { fmtDate, fmtValue } from "@/lib/format";
import { isCorrection, MONTHS, yearFraction } from "@/lib/scene";
import type { HistoryRow } from "@/lib/types";

// Valid time runs across, knowledge version runs down, like lines added to a ledger.
const W = 1000;
const LEFT = 56;
const RIGHT = 24;
const TOP = 30;
const ROW = 64;
const PLOT = W - LEFT - RIGHT;
const YEAR_W = (PLOT * 12) / 13; // the 13th column is "2025 and later"
const x = (iso: string | null) => (iso === null ? LEFT + PLOT : LEFT + yearFraction(iso) * YEAR_W);

type Props = {
  attribute: string;
  rows: HistoryRow[];
  versions: number;
  selected: number;
  onSelect: (v: number) => void;
};

export function Bitemporal({ attribute, rows, versions, selected, onSelect }: Props) {
  const svg = useRef<SVGSVGElement>(null);
  const H = TOP + ROW * versions + 8;
  const y = (v: number) => TOP + ROW * (v - 1);

  const pick = (clientY: number) => {
    const box = svg.current?.getBoundingClientRect();
    if (!box) return;
    const v = Math.floor(((clientY - box.top) * (H / box.height) - TOP) / ROW) + 1;
    onSelect(Math.min(versions, Math.max(1, v)));
  };

  return (
    <svg
      ref={svg}
      className="bitemporal"
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`What was known about ${attribute} at each version`}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        pick(e.clientY);
      }}
      onPointerMove={(e) => e.buttons && pick(e.clientY)}
    >
      <defs>
        <pattern id="struck" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2="7" className="hatch" />
        </pattern>
      </defs>

      {MONTHS.map((m, i) => (
        <g key={m}>
          <line className="grid" x1={LEFT + (YEAR_W * i) / 12} x2={LEFT + (YEAR_W * i) / 12} y1={TOP - 6} y2={H - 8} />
          <text className="tick" x={LEFT + (YEAR_W * (i + 0.5)) / 12} y={TOP - 12} textAnchor="middle">
            {m}
          </text>
        </g>
      ))}
      <line className="grid" x1={LEFT + YEAR_W} x2={LEFT + YEAR_W} y1={TOP - 6} y2={H - 8} />
      <text className="tick" x={LEFT + YEAR_W + (PLOT - YEAR_W) / 2} y={TOP - 12} textAnchor="middle">
        2025+
      </text>

      {Array.from({ length: versions }, (_, i) => i + 1).map((v) => (
        <g key={v} className={v === selected ? "version on" : "version"}>
          <rect className="band" x={0} y={y(v)} width={W} height={ROW} />
          <rect className="marker" x={0} y={y(v)} width={4} height={ROW} />
          <text className="vlabel" x={LEFT - 14} y={y(v) + ROW / 2 + 5} textAnchor="end">
            v{v}
          </text>
        </g>
      ))}

      {rows.map((r) => {
        const x0 = x(r.from);
        const x1 = x(r.to);
        if (x1 - x0 < 1) return null;
        const y0 = y(r.tx_from) + 8;
        const y1 = (r.tx_to === null ? y(versions + 1) : y(r.tx_to)) - 8;
        const live = r.tx_from <= selected && (r.tx_to === null || r.tx_to > selected);
        const cls = [
          "fact",
          r.tx_to !== null ? "superseded" : "",
          isCorrection(rows, r, r.tx_from) ? "correction" : "",
          live ? "live" : "dim",
        ].join(" ");
        return (
          <g key={`${r.tx_from}:${r.from}`} className={cls}>
            <rect x={x0} y={y0} width={x1 - x0} height={y1 - y0} />
            <text x={x0 + 10} y={y0 + 22}>
              {fmtValue(attribute, r.value)}
            </text>
            <text className="sub" x={x0 + 10} y={y0 + 40}>
              from {fmtDate(r.from)}, written v{r.tx_from}
              {r.tx_to !== null ? `, replaced v${r.tx_to}` : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
