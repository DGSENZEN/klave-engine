"use client";

import { useEffect, useRef } from "react";
import { cssVar, getTheme, subscribeTheme, type Theme } from "@/lib/theme";
import type { PondPalette, Rgb } from "@/lib/ascii-pond/pond";

/**
 * The koi pond behind the auth screens, drawn in Klave's own tokens: ink
 * bodies, cobalt markings, the page's exact background. Decoration only — the
 * canvas is aria-hidden, slows to a fifth under reduced motion and hides in
 * forced-colours mode (all handled by the engine).
 */
export function AsciiPond({ className = "" }: { className?: string }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let disposed = false;
    let stop = () => {};

    // The engine defines a custom element at import time, so it loads only in the browser.
    import("@/lib/ascii-pond/pond.js").then(({ mount }) => {
      if (disposed) return;
      const theme = getTheme();
      const pond = mount(element, {
        theme,
        fixed: false,
        avoid: "[data-pond-avoid]",
        palette: { [theme]: tokenPalette(theme) },
      });
      const mono = cssVar("--font-geist-mono");
      if (mono) pond.renderer.fontFamily = `${mono}, ui-monospace, monospace`;

      const unsubscribe = subscribeTheme((next) => {
        // Tokens are only readable for the theme on screen, so refresh that palette as it arrives.
        Object.assign(pond.renderer.themes[next], tokenPalette(next));
        // Wipe from the corner nearest the theme toggle.
        pond.setTheme(next === "light", { x: pond.canvas.clientWidth, y: 0 });
      });
      stop = () => {
        unsubscribe();
        pond.destroy();
      };
    });

    return () => {
      disposed = true;
      stop();
    };
  }, []);

  return <div ref={host} aria-hidden="true" className={className} />;
}

function rgb(token: string): Rgb {
  const hex = cssVar(token).replace("#", "");
  const n = parseInt(hex.length === 3 ? hex.replace(/./g, "$&$&") : hex, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function mix(a: Rgb, b: Rgb, k: number): Rgb {
  return [0, 1, 2].map((i) => Math.round(a[i] + (b[i] - a[i]) * k)) as Rgb;
}

/** The engine's palette keys, filled from the current theme's CSS tokens. */
function tokenPalette(theme: Theme): PondPalette {
  const background = rgb("--background");
  const foreground = rgb("--foreground");
  const muted = rgb("--muted");
  const faint = rgb("--faint");
  const accent = rgb("--accent");
  // Koi markings: the one accent, from deep shadow to lit highlight.
  const hi = [-0.7, -0.45, -0.2, 0, 0.3, 0.55].map((k) =>
    k < 0 ? mix(accent, [0, 0, 0], -k) : mix(accent, [255, 255, 255], k),
  );
  const shared = { page: background, fg: foreground, water: foreground, pellet: accent, red: accent, hi };
  return theme === "dark"
    ? { ...shared, bg: rgb("--surface"), white: foreground, black: faint, fin: mix(foreground, muted, 0.5), eye: background }
    : { ...shared, bg: background, white: muted, black: foreground, fin: mix(muted, faint, 0.5), eye: foreground };
}
