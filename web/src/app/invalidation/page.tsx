import type { Metadata } from "next";
import { Invalidation } from "@/components/Invalidation";

export const metadata: Metadata = { title: "Invalidation" };

export default function Page() {
  return <Invalidation />;
}
