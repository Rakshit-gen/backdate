import { describe, expect, it } from "vitest";
import { affectedBy, knownAt, overlaps, yearFraction } from "./scene";
import type { Changeset, Graph } from "./types";

describe("overlaps", () => {
  it("treats ranges as half-open", () => {
    expect(overlaps({ from: "2024-01-01", to: "2024-02-01" }, { from: "2024-02-01", to: null })).toBe(false);
    expect(overlaps({ from: "2024-01-01", to: "2024-02-02" }, { from: "2024-02-01", to: null })).toBe(true);
    expect(overlaps({ from: "2024-03-01", to: null }, { from: "2030-01-01", to: null })).toBe(true);
  });
});

it("knownAt keeps rows believed at that version", () => {
  const rows = [
    { from: "2024-01-01", to: null, value: 1, tx_from: 2, tx_to: 3 },
    { from: "2024-01-01", to: null, value: 2, tx_from: 3, tx_to: null },
  ];
  expect(knownAt(rows, 1)).toEqual([]);
  expect(knownAt(rows, 2).map((r) => r.value)).toEqual([1]);
  expect(knownAt(rows, 9).map((r) => r.value)).toEqual([2]);
});

it("yearFraction clamps to 2024", () => {
  expect(yearFraction("2024-01-01")).toBe(0);
  expect(yearFraction(null)).toBe(1);
  expect(yearFraction("2023-06-01")).toBe(0);
  expect(yearFraction("2024-07-02")).toBeCloseTo(0.5, 2);
});

describe("affectedBy", () => {
  const comp = (id: number, key: string, reads: Graph["computations"][number]["reads"]) =>
    ({ id, key, derivation: "x", reads }) as unknown as Graph["computations"][number];
  const salary = (from: string, to: string) => ({ entity: "employee:7", attribute: "annual_salary_cents", from, to });
  const graph: Graph = {
    version: 3,
    truncated: false,
    computations: [
      comp(1, "7:2024-02", [salary("2024-02-01", "2024-03-01")]),
      comp(2, "7:2024-03", [salary("2024-03-01", "2024-04-01")]),
      comp(3, "7:2024-03", []),
    ],
    edges: [{ source: 2, reader: 3, observed_seq: 1 }],
  };
  const raise: Changeset = {
    version: 3,
    recorded_at: "",
    actor: "",
    reason: "",
    changes: [{ entity: "employee:7", attribute: "annual_salary_cents", from: "2024-03-01", to: null }],
  };

  it("finds direct readers and their dependents, not earlier months", () => {
    expect([...affectedBy(raise, graph)]).toEqual([
      [2, 0],
      [3, 1],
    ]);
  });
});
