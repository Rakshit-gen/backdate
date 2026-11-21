import { cents } from "./payroll";
import { MONTHS } from "./scene";

export function fmtDate(iso: string | null): string {
  if (iso === null) return "onwards";
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[(m ?? 1) - 1]} ${y}`;
}

export const ATTRIBUTE_NAMES: Record<string, string> = {
  annual_salary_cents: "Salary",
  fte_bp: "FTE",
  state: "State",
  withholding_bp: "Withholding rate",
};

export function fmtValue(attribute: string, value: unknown): string {
  if (attribute === "annual_salary_cents" && typeof value === "number") return `${cents(value)} a year`;
  if (attribute === "fte_bp" && typeof value === "number") return (value / 10_000).toFixed(2);
  if (attribute === "withholding_bp" && typeof value === "number") return `${(value / 100).toFixed(2)}%`;
  return String(value);
}

export function fmtTime(iso: string): string {
  // UTC, so the server and the browser render the same text.
  return `${new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "UTC" })} UTC`;
}
