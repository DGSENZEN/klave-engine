import { apiMessage } from "./api";
import { ApiError } from "./httpErrors";

export type DrawingUploadLimits = { max_files: number; max_file_bytes: number };

const MIB = 1024 * 1024;

/** Lo que el API acepta por archivo (`max_upload_bytes`) si el taller no dice otra cosa. */
export const DEFAULT_MAX_FILE_BYTES = 100 * MIB;

/**
 * Todas las hojas viajan en una sola petición y el proxy corta el cuerpo
 * completo en 120 MB decimales. 110 MiB (≈ 115 MB decimales) deja margen
 * para el sobre multipart sin rozar ese corte.
 */
export const MAX_BATCH_BYTES = 110 * MIB;

const MB_FORMAT = new Intl.NumberFormat("es-MX", { maximumFractionDigits: 1 });

/** Tamaño legible en MB (base 1024, como el límite del API). */
export function formatMegabytes(bytes: number): string {
  return MB_FORMAT.format(bytes / MIB) + " MB";
}

const EN_PARTES =
  "Sube primero una parte de las hojas y agrega el resto después desde «Hojas del proyecto», en el resumen de la obra.";

export function validateDrawingFiles(
  files: readonly Pick<File, "name" | "size">[],
  limits?: DrawingUploadLimits,
): string | null {
  if (!files.length) return "Selecciona al menos un plano DWG o DXF.";
  if (files.length > (limits?.max_files ?? 40)) return "La selección supera el límite de hojas del proyecto. Reduce la selección e inténtalo de nuevo.";
  const unsupported = files.find((file) => !/\.(dwg|dxf)$/i.test(file.name));
  if (unsupported) return `«${unsupported.name}» no es un plano DWG o DXF. Revisa la selección.`;
  const empty = files.find((file) => file.size === 0);
  if (empty) return `«${empty.name}» está vacío. Exporta el plano de nuevo antes de subirlo.`;
  const maxFile = limits?.max_file_bytes ?? DEFAULT_MAX_FILE_BYTES;
  const oversized = files.find((file) => file.size > maxFile);
  if (oversized) {
    return `«${oversized.name}» pesa ${formatMegabytes(oversized.size)} y el límite es ${formatMegabytes(maxFile)} por archivo. Exporta una versión más pequeña.`;
  }
  // Cada archivo cabe, pero el envío completo puede no caber: sin esta
  // revisión la subida moría a medio camino con un error genérico.
  const total = files.reduce((sum, file) => sum + file.size, 0);
  if (total > MAX_BATCH_BYTES) {
    return `La selección suma ${formatMegabytes(total)} y una subida admite hasta ${formatMegabytes(MAX_BATCH_BYTES)}. ${EN_PARTES}`;
  }
  return null;
}

/**
 * El mensaje de una subida fallida. Un 413 es tamaño (o número de hojas, que
 * el servidor ya explica con su propio mensaje); lo demás pasa por apiMessage.
 */
export function uploadErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.status === 413) {
    const detail = error.detail && typeof error.detail === "object"
      ? (error.detail as { error_type?: unknown; max_upload_bytes?: unknown })
      : {};
    if (detail.error_type === "too_many_files") return apiMessage(error, fallback);
    const maxFile = typeof detail.max_upload_bytes === "number" ? detail.max_upload_bytes : DEFAULT_MAX_FILE_BYTES;
    return `El servidor rechazó la subida por tamaño: admite hasta ${formatMegabytes(maxFile)} por archivo y ${formatMegabytes(MAX_BATCH_BYTES)} por subida. ${EN_PARTES}`;
  }
  return apiMessage(error, fallback);
}
