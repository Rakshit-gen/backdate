import type { Metadata } from "next";
import { Payroll } from "@/components/Payroll";

export const metadata: Metadata = { title: "Payroll" };

// The home page links here with ?from=6&salary=86000 to carry over the raise it simulated.
export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const q = await searchParams;
  const month = Number(q.from);
  const salary = Number(q.salary);
  return (
    <Payroll
      initialMonth={Number.isInteger(month) && month >= 1 && month <= 12 ? month : undefined}
      initialSalary={Number.isInteger(salary) && salary > 0 && salary <= 1_000_000 ? salary : undefined}
    />
  );
}
