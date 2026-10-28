"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";

/**
 * What one access screen puts in the frame (app/(acceso)/layout.tsx): a
 * heading, the task, and at most one line below it. Keep `sub` to a sentence.
 */
export function AuthFrame({
  title,
  sub,
  children,
  footer,
}: {
  title: string;
  sub?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="rise-in">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {sub && <p className="mt-1.5 text-sm text-muted">{sub}</p>}
      <div className="mt-7">{children}</div>
      {footer && <div className="mt-8 text-center text-sm text-muted">{footer}</div>}
    </div>
  );
}

/** Entrar / Crear cuenta as two routes, so either is one click and the back button works. */
export function AuthSwitch({ current }: { current: "entrar" | "registro" }) {
  const tabs = [
    { key: "entrar", href: "/bienvenida", label: "Entrar" },
    { key: "registro", href: "/registro", label: "Crear cuenta" },
  ] as const;
  return (
    <nav aria-label="Acceso" className="mb-6 flex rounded-lg bg-surface-2 p-0.5">
      {tabs.map((tab) => (
        <Link
          key={tab.key}
          href={tab.href}
          aria-current={tab.key === current ? "page" : undefined}
          className={`flex-1 rounded-md px-3 py-1.5 text-center text-sm font-medium transition-colors ${
            tab.key === current
              ? "bg-surface text-foreground shadow-xs"
              : "text-muted hover:text-foreground"
          }`}
        >
          {tab.label}
        </Link>
      ))}
    </nav>
  );
}

/** Reads a query parameter after mount (no Suspense, no hydration drift). */
export function useQueryParam(name: string): string | null | undefined {
  // undefined = not read yet; null = absent.
  const [value, setValue] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    const handle = window.setTimeout(() => {
      setValue(new URLSearchParams(window.location.search).get(name));
    }, 0);
    return () => window.clearTimeout(handle);
  }, [name]);
  return value;
}
