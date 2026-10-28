"use client";

import { useSyncExternalStore } from "react";
import { Moon, Sun } from "@phosphor-icons/react";
import { getTheme, setTheme, subscribeTheme, type Theme } from "@/lib/theme";
import { iconButtonClasses } from "@/components/ui";

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
      data-tip={theme === "dark" ? "Tema claro" : "Tema oscuro"}
      data-tip-align="end"
      className={iconButtonClasses("md", className)}
    >
      {theme === "dark" ? <Sun /> : <Moon />}
    </button>
  );
}
