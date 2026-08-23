/**
 * Numbers, money and labels the way an estimator in Mexico reads them.
 * Everything user-facing that turns a value into text lives here, so two
 * pages never format the same thing two ways.
 */

export const money = (n: number, currency = "MXN") =>
  new Intl.NumberFormat("es-MX", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(n);

export const money2 = (n: number, currency = "MXN") =>
  new Intl.NumberFormat("es-MX", { style: "currency", currency }).format(n);

export const num = (n: number, digits = 2) =>
  new Intl.NumberFormat("es-MX", { maximumFractionDigits: digits }).format(n);

/** Percent from a 0–1 ratio, no decimals: 0.734 → "73 %". */
export const pct = (ratio: number) => `${Math.round(ratio * 100)} %`;

export const RESOURCE_TYPE_LABELS: Record<string, string> = {
  material: "Material",
  mano_de_obra: "Mano de obra",
  equipo: "Equipo",
  herramienta: "Herramienta",
  subcontrato: "Subcontrato",
};

/** The enum value the API speaks ("mano_de_obra") as the words on screen. */
export const resourceTypeLabel = (type: string) => RESOURCE_TYPE_LABELS[type] ?? type;

/** One CSV cell: quoted when it contains a comma, quote or newline. */
function csvCell(value: unknown): string {
  if (value == null) return "";
  const text = typeof value === "number" ? String(value) : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** Rows → a UTF-8 CSV file the browser saves (BOM so Excel reads accents). */
export function downloadCsv(filename: string, rows: unknown[][]): void {
  const csv = rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
  const blob = new Blob(["﻿", csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
