import type { Metadata } from "next";
import { Payroll } from "@/components/Payroll";

export const metadata: Metadata = { title: "Payroll" };

export default function Page() {
  return <Payroll />;
}
