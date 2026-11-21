import type { Metadata } from "next";
import { Workers } from "@/components/Workers";

export const metadata: Metadata = { title: "Workers" };

export default function Page() {
  return <Workers />;
}
