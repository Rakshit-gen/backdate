import { describe, expect, it } from "vitest";
import { edgeBuffers, layout, nodeStart } from "./loom";
import type { Changeset, Graph } from "./types";

const read = (attribute: string, from: string, to: string) => ({ entity: "employee:7", attribute, from, to });
const comp = (id: number, derivation: string, key: string, reads: ReturnType<typeof read>[]) =>
  ({ id, derivation, key, reads }) as unknown as Graph["computations"][number];

const graph: Graph = {
  version: 3,
  truncated: false,
  computations: [
    comp(1, "payroll.gross", "7:2024-02", [read("annual_salary_cents", "2024-02-01", "2024-03-01")]),
    comp(2, "payroll.gross", "7:2024-03", [read("annual_salary_cents", "2024-03-01", "2024-04-01")]),
    comp(3, "payroll.withholding", "7:2024-03", [read("state", "2024-03-31", "2024-04-01")]),
  ],
  edges: [{ source: 2, reader: 3, observed_seq: 1 }],
};
const change: Changeset = {
  version: 3,
  recorded_at: "",
  actor: "",
  reason: "",
  changes: [{ entity: "employee:7", attribute: "annual_salary_cents", from: "2024-03-01", to: null }],
};

describe("layout", () => {
  const l = layout(graph, change);
  it("orders lanes salary first", () => {
    expect(l.lanes.map((x) => x.attribute)).toEqual(["annual_salary_cents", "state"]);
  });
  it("inks only edges whose read overlaps the change", () => {
    expect(l.edges.map((e) => e.start >= 0)).toEqual([false, true, false, true]);
  });
  it("lights dependents after the results they read", () => {
    expect(l.nodes.map((n) => n.depth)).toEqual([null, 0, 1]);
    expect(nodeStart(1)).toBeGreaterThan(nodeStart(0));
  });
});

it("builds two vertices per point and two triangles per segment", () => {
  const b = edgeBuffers([
    {
      points: [
        [0, 0],
        [10, 0],
        [20, 0],
      ],
      start: 0,
      width: 2,
    },
  ]);
  expect(b.position.length).toBe(3 * 2 * 3);
  expect(b.index.length).toBe(2 * 6);
  expect([...b.along]).toEqual([0, 0, 0.5, 0.5, 1, 1]);
});
