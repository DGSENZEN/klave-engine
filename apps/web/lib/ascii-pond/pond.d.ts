// Types for the vendored ascii-pond engine (MIT, see LICENSE).
// Upstream: https://github.com/stqfdyr/ascii-pond @ 822a3c95167f79f0905720a2e6793cb4a64eda55
// pond.js, koi.js and util.js are copied verbatim; change them only by re-vendoring.

export type Rgb = [number, number, number];

/** Palette keys the engine and the koi species read; every key is optional in an override. */
export type PondPalette = Partial<{
  page: Rgb;
  fg: Rgb;
  bg: Rgb;
  water: Rgb;
  shadow: Rgb;
  shadowAlpha: number;
  pellet: Rgb;
  alpha: number;
  depthFloor: number;
  tile: [number, number];
  ink: number;
  white: Rgb;
  red: Rgb;
  black: Rgb;
  fin: Rgb;
  eye: Rgb;
  hi: Rgb[];
}>;

export type PondOptions = {
  species?: Array<string | { type: string; count?: number | "auto"; young?: number | "auto" }>;
  theme?: "auto" | "dark" | "light";
  avoid?: string | null;
  ignore?: string;
  feed?: boolean;
  fixed?: boolean;
  speed?: number;
  palette?: { dark?: PondPalette; light?: PondPalette };
};

export type PondInstance = {
  canvas: HTMLCanvasElement;
  renderer: { fontFamily: string; themes: { dark: PondPalette; light: PondPalette } };
  feed(x: number, y: number): void;
  measure(): void;
  setTheme(isLight: boolean, at?: { x: number; y: number }): void;
  destroy(): void;
};

export function mount(target: HTMLElement, options?: PondOptions): PondInstance;
