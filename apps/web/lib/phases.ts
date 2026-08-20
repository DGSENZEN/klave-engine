// Stable colors for construction phases, resolved through the chart tokens so
// both themes stay consistent. Unknown phases fall back by position.

const KNOWN_PHASE_COLORS: Record<string, string> = {
  Preliminares: "var(--chart-2)",
  Cimentación: "var(--chart-3)",
  Estructura: "var(--chart-1)",
};

const FALLBACK = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
];

export function phaseColor(phase: string, index = 0): string {
  return KNOWN_PHASE_COLORS[phase] ?? FALLBACK[index % FALLBACK.length];
}
