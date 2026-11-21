import { expect, it } from "vitest";
import { signed } from "./story";

it("signs money with a real minus", () => {
  expect(signed(10871200)).toBe("+108,712.00");
  expect(signed(-5)).toBe("−0.05");
  expect(signed(0)).toBe("0.00");
});
