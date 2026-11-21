import { expect, it } from "vitest";
import { ledger, stored } from "./feed";
import type { Computation, Restatement } from "./types";

const r = (key: string, v: number, prev: number | null, cur: number): Restatement => ({
  computation: { id: key.length, derivation: "payroll.gross", key },
  seq: prev === null ? 1 : 2,
  from_version: prev === null ? null : v - 1,
  to_version: v,
  previous: prev === null ? null : { gross_cents: prev },
  current: { gross_cents: cur },
  delta: { gross_cents: cur - (prev ?? 0) },
  created_at: "",
});

const feed = [r("7:2024-03", 2, null, 49973), r("7:2024-04", 2, null, 387288), r("7:2024-03", 3, 49973, 64000)];

it("groups by version and sums deltas into a balance", () => {
  const all = ledger(feed, "payroll.gross", 3);
  expect(all.groups.map(([v, ls]) => [v, ls.length])).toEqual([
    [2, 2],
    [3, 1],
  ]);
  expect(all.balance).toBe(64000 + 387288);
  expect(ledger(feed, "payroll.gross", 2).balance).toBe(49973 + 387288);
});

it("matches the stored results at the latest version", () => {
  const comps = [
    { derivation: "payroll.gross", result: { gross_cents: 64000 } },
    { derivation: "payroll.gross", result: { gross_cents: 387288 } },
  ] as unknown as Computation[];
  expect(stored(comps, "payroll.gross")).toBe(ledger(feed, "payroll.gross", 3).balance);
});
