"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** Programa de obra and flujo financiero are one delivery: two views of the same schedule. */
export function ProgramaFlujoTabs({ id }: { id: string }) {
  const pathname = usePathname();
  const items = [
    { href: `/proyecto/${id}/programa`, label: "Programa de obra" },
    { href: `/proyecto/${id}/flujo`, label: "Flujo financiero" },
  ];
  return (
    <div role="tablist" className="mb-5 flex gap-1 border-b border-border">
      {items.map((item) => {
        const active = pathname === item.href;
        return (
          <Link
            key={item.href}
            href={item.href}
            role="tab"
            aria-selected={active}
            className={`-mb-px border-b-2 px-3 py-2.5 text-sm transition-colors ${
              active
                ? "border-foreground font-medium text-foreground"
                : "border-transparent text-muted hover:text-foreground"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </div>
  );
}
