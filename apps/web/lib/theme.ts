// Theme handling: an explicit user choice persists in localStorage; otherwise
// the OS preference wins. The <html data-theme> attribute is the single source
// of truth and is stamped before first paint by the inline script in layout.tsx.

export type Theme = "light" | "dark";

export const THEME_KEY = "klave.theme";

/** Runs before hydration; keep it dependency-free and ES5-safe. */
export const THEME_INIT_SCRIPT = `(function(){try{var t=localStorage.getItem("${THEME_KEY}");if(t!=="light"&&t!=="dark"){t=window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme="light"}})()`;

export function getTheme(): Theme {
  if (typeof document === "undefined") return "light";
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function setTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {}
}

/** Notifies when data-theme changes (e.g. the canvas re-reads its palette). */
export function subscribeTheme(onChange: (theme: Theme) => void): () => void {
  if (typeof document === "undefined") return () => {};
  const observer = new MutationObserver(() => onChange(getTheme()));
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
  return () => observer.disconnect();
}

/** Reads a CSS custom property from the current theme (for canvas drawing). */
export function cssVar(name: string): string {
  if (typeof window === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}
