// The arithmetic of examples/payroll/derivations.py, for the in-browser simulation.
// Integers only: a day's pay is annual * fte_bp / (365 * 10000), summed exactly as a
// fraction and rounded once, half to even, like the Python version.

export type Piece<T> = { start: string; end: string | null; value: T };

const DAY = 86_400_000;
const DENOM = 365 * 10_000;

export function roundHalfEven(num: number, den: number): number {
  const q = Math.floor(num / den);
  const r = num - q * den;
  if (r * 2 < den) return q;
  if (r * 2 > den) return q + 1;
  return q % 2 === 0 ? q : q + 1;
}

const toDay = (iso: string) => Date.parse(`${iso}T00:00:00Z`) / DAY;

function valueOn<T>(pieces: Piece<T>[], day: number): T | undefined {
  for (const p of pieces) {
    if (toDay(p.start) <= day && (p.end === null || day < toDay(p.end))) return p.value;
  }
  return undefined;
}

export function monthBounds(year: number, month: number): [number, number] {
  return [Date.UTC(year, month - 1, 1) / DAY, Date.UTC(year, month, 1) / DAY];
}

export function gross(
  salary: Piece<number>[],
  fte: Piece<number>[],
  year: number,
  month: number,
): { gross_cents: number; days_paid: number } {
  const [from, to] = monthBounds(year, month);
  let num = 0;
  let days = 0;
  for (let d = from; d < to; d++) {
    const annual = valueOn(salary, d);
    const share = valueOn(fte, d);
    if (annual === undefined || share === undefined) continue;
    days++;
    num += annual * share;
  }
  return { gross_cents: roundHalfEven(num, DENOM), days_paid: days };
}

export function withholding(grossCents: number, rateBp: number): number {
  return roundHalfEven(grossCents * rateBp, 10_000);
}

/** Timeline after asserting `value` from `start` onwards, as the backend's timeline algebra does. */
export function assertFrom<T>(pieces: Piece<T>[], start: string, value: T): Piece<T>[] {
  const s = toDay(start);
  const out: Piece<T>[] = [];
  for (const p of pieces) {
    if (toDay(p.start) >= s) continue;
    out.push(p.end !== null && toDay(p.end) <= s ? p : { ...p, end: start });
  }
  out.push({ start, end: null, value });
  return out;
}

export const cents = (n: number) =>
  (n / 100).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
