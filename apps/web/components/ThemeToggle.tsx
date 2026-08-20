"use client";

import { useSyncExternalStore } from "react";
import { Moon, Sun } from "@phosphor-icons/react";
import { getTheme, setTheme, subscribeTheme, type Theme } from "@/lib/theme";

function subscribe(onStoreChange: () => void): () => void {
  return subscribeTheme(onStoreChange);
}

export function ThemeToggle({ className = "" }: { className?: string }) {
  // The server doesn't know the theme; snapshot "light" until hydration.
  const theme = useSyncExternalStore(subscribe, getTheme, (): Theme => "light");
  const next: Theme = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={theme === "dark" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
      title={theme === "dark" ? "Tema claro" : "Tema oscuro"}
      className={`inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border bg-surface text-muted transition hover:bg-surface-2 hover:text-foreground ${className}`}
    >
      {theme === "dark" ? <Sun size={15} /> : <Moon size={15} />}
    </button>
  );
}
