"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

// In the order a backdate happens, so each page can point at the next one.
export const PAGES = [
  { href: "/payroll", label: "Payroll", next: "Backdate a raise and see each month's pay change" },
  { href: "/invalidation", label: "Invalidation", next: "See which results the correction marked stale, and why" },
  { href: "/workers", label: "Workers", next: "Watch workers recompute them under leases" },
  { href: "/feed", label: "Feed", next: "Read the corrections they published" },
  { href: "/benchmarks", label: "Benchmarks", next: "Check how fast all of this is" },
] as const;

/** A link to the next step at the bottom of every page. */
export function NextStep() {
  const path = usePathname();
  const i = path === "/" ? -1 : PAGES.findIndex((p) => p.href === path);
  const next = PAGES[i + 1];
  return (
    <nav className="next-step" aria-label="Next step">
      {next ? (
        <Link href={next.href}>
          <span className="muted">Next: {next.label}</span>
          {next.next}
        </Link>
      ) : (
        <Link href="/">
          <span className="muted">That&rsquo;s the whole path</span>
          Back to the start
        </Link>
      )}
    </nav>
  );
}

export function Header() {
  const path = usePathname();
  return (
    <header className="site-header">
      <a href="#main" className="skip">
        Skip to content
      </a>
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
