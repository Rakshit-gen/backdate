"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export const PAGES = [
  { href: "/payroll", label: "Payroll" },
  { href: "/invalidation", label: "Invalidation" },
  { href: "/workers", label: "Workers" },
  { href: "/feed", label: "Feed" },
  { href: "/benchmarks", label: "Benchmarks" },
] as const;

export function Header() {
  const path = usePathname();
  return (
    <header className="site-header">
      <Link href="/" className="wordmark" aria-current={path === "/" ? "page" : undefined}>
        backdate
      </Link>
      <nav aria-label="Pages">
        {PAGES.map((p) => (
          <Link key={p.href} href={p.href} aria-current={path === p.href ? "page" : undefined}>
            {p.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
