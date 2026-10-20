export type DrawingUploadLimits = { max_files: number; max_file_bytes: number };

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
  const oversized = limits && files.find((file) => file.size > limits.max_file_bytes);
  if (oversized) return "«" + oversized.name + "» supera el tamaño permitido por archivo. Exporta una versión más pequeña.";
  return null;
}
