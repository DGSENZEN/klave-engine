"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { Buildings } from "@phosphor-icons/react";
import { ThemeToggle } from "@/components/ThemeToggle";

/**
 * The one frame for every standalone auth screen (bienvenida, recuperar,
 * restablecer, invitación, verificar). Same mark, same place, same width —
 * a user recovering a password at 7 a.m. should not have to re-learn a layout.
 */
export function AuthFrame({
  title,
  sub,
  children,
  footer,
  width = "md",
}: {
  title: string;
  sub?: string;
  children: ReactNode;
  footer?: ReactNode;
  width?: "md" | "lg";
}) {
  return (
    <div
      className={`mx-auto flex min-h-screen ${
        width === "lg" ? "max-w-2xl" : "max-w-md"
      } flex-col justify-center px-5 py-10 sm:px-6`}
    >
      <div className="rise-in">
        <div className="mb-8 flex items-start justify-between gap-4">
          <Link href="/bienvenida" className="flex items-center gap-3.5">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-fg">
              <Buildings size={22} weight="duotone" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
              {sub && <p className="text-sm text-muted">{sub}</p>}
            </div>
          </Link>
          <ThemeToggle />
        </div>
        {children}
        {footer && <div className="mt-6 text-center text-sm text-muted">{footer}</div>}
      </div>
    </div>
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
