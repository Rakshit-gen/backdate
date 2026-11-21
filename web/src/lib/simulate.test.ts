import { expect, it } from "vitest";
import { changedSpans } from "./simulate";

const salary = [
  { start: "2024-03-01", end: "2024-06-01", value: 7_300_000 },
  { start: "2024-06-01", end: null, value: 7_800_000 },
];

it("a raise changes everything from its start date", () => {
  expect(changedSpans(salary, "2024-04-01", 9_000_000)).toEqual([{ from: "2024-04-01", to: null }]);
});

it("dates that already had the value are not a change", () => {
  expect(changedSpans(salary, "2024-01-01", 7_300_000)).toEqual([
    { from: "2024-01-01", to: "2024-03-01" },
    { from: "2024-06-01", to: null },
  ]);
  expect(changedSpans(salary, "2024-06-01", 7_800_000)).toEqual([]);
});
