import type { Metadata } from "next";
import { Feed } from "@/components/Feed";

export const metadata: Metadata = { title: "Feed" };

export default function Page() {
  return <Feed />;
}
