import { Badge } from "@/components/ui";

/**
 * De qué capa viene una fila del catálogo. Es la misma insignia en la hoja
 * de insumos, en la de conceptos y en las partidas del presupuesto: cuatro
 * palabras, cuatro tonos, aprendidas una vez. El origen exacto (la
 * publicación y su clave, el archivo importado, la plantilla) va en el
 * título, no en la fila.
 */
export type Origen = "oficial" | "importada" | "generada" | "taller";

const LABELS: Record<Origen, string> = {
  oficial: "Oficial",
  importada: "Importada",
  generada: "Generada",
  taller: "Taller",
};

const TONES: Record<Origen, "success" | "accent" | "warning" | "default"> = {
  oficial: "success",
  importada: "accent",
  generada: "warning",
  taller: "default",
};

export function OrigenBadge({
  origin,
  originRef,
  verdict,
}: {
  origin?: string | null;
  originRef?: string | null;
  verdict?: string | null;
}) {
  const key: Origen = (["oficial", "importada", "generada", "taller"] as Origen[]).includes(
    origin as Origen,
  )
    ? (origin as Origen)
    : "taller";
  const detail = [originRef, verdict ? `validación: ${verdict.replace(/_/g, " ")}` : ""]
    .filter(Boolean)
    .join(" · ");
  return (
    <span title={detail || undefined}>
      <Badge tone={TONES[key]}>{LABELS[key]}</Badge>
    </span>
  );
}
