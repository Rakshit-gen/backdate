import { describe, expect, it } from "vitest";
import { assertFrom, gross, roundHalfEven, withholding } from "./payroll";

describe("roundHalfEven", () => {
  it("rounds halves to the even neighbour", () => {
    expect(roundHalfEven(5, 2)).toBe(2);
    expect(roundHalfEven(7, 2)).toBe(4);
    expect(roundHalfEven(7, 3)).toBe(2);
    expect(roundHalfEven(8, 3)).toBe(3);
  });
});

describe("gross matches the Python derivation", () => {
  // Employee 7 from the README's quick-start run: hired 28 March at 0.8 FTE on
  // 5,700,000 cents, then a raise to 7,300,000 backdated to 1 March.
  const fte = [{ start: "2024-03-28", end: null, value: 8_000 }];
  const before = [{ start: "2024-03-28", end: null, value: 5_700_000 }];

  it("gives the same cents as the backend before the raise", () => {
    expect(gross(before, fte, 2024, 3)).toEqual({ gross_cents: 49_973, days_paid: 4 });
    expect(gross(before, fte, 2024, 5).gross_cents).toBe(387_288);
    expect(gross(before, fte, 2024, 6).gross_cents).toBe(374_795);
  });

  it("pays only the days employed", () => {
    expect(gross(before, fte, 2024, 3).days_paid).toBe(4);
  });

  it("gives the same cents as the backend after the raise", () => {
    const after = assertFrom(before, "2024-03-01", 7_300_000);
    expect(gross(after, fte, 2024, 3)).toEqual({ gross_cents: 64_000, days_paid: 4 });
    expect(gross(after, fte, 2024, 5)).toEqual({ gross_cents: 496_000, days_paid: 31 });
    expect(gross(after, fte, 2024, 6)).toEqual({ gross_cents: 480_000, days_paid: 30 });
  });

  it("withholds at the rate in basis points", () => {
    expect(withholding(496_000, 1_000)).toBe(49_600);
    expect(withholding(5, 1_000)).toBe(0);
    expect(withholding(15, 1_000)).toBe(2);
  });
});

describe("assertFrom", () => {
  it("cuts the piece that straddles the start", () => {
    const t = assertFrom([{ start: "2024-01-01", end: null, value: 1 }], "2024-03-01", 2);
    expect(t).toEqual([
      { start: "2024-01-01", end: "2024-03-01", value: 1 },
      { start: "2024-03-01", end: null, value: 2 },
    ]);
  });
});
