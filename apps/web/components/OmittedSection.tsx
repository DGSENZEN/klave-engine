"use client";

import { useCallback, useEffect, useState } from "react";
import { PlusCircle, Trash } from "@phosphor-icons/react";
import {
  addOmittedElement,
  getProjectReviews,
  removeOmittedElement,
  type OmittedElement,
} from "@/lib/api";
import { Button, Callout, Card, Input, SectionTitle, Select } from "@/components/ui";

/** What each family needs from the engineer: nothing beyond the count, a
 * total length, or a total area. Mirrors the API's validation. */
const FAMILIES: { value: string; label: string; measure: "none" | "length" | "area" }[] = [
  { value: "castillo", label: "Castillo", measure: "none" },
  { value: "columna", label: "Columna", measure: "none" },
  { value: "trabe", label: "Trabe", measure: "length" },
  { value: "contratrabe", label: "Contratrabe", measure: "length" },
  { value: "dala", label: "Dala", measure: "length" },
  { value: "cerramiento", label: "Cerramiento", measure: "length" },
  { value: "zapata", label: "Zapata", measure: "area" },
  { value: "pilote", label: "Pilote", measure: "none" },
  { value: "muro", label: "Muro", measure: "length" },
  { value: "muro_concreto", label: "Muro de concreto", measure: "length" },
  { value: "losa", label: "Losa", measure: "area" },
  { value: "escalera", label: "Escalera", measure: "area" },
];

/**
 * The inverse of an exclusion: record what the engine missed. It joins the
 * presupuesto as levantamiento manual with the engineer's name on it — and
 * it doubles as a recall report of the engine's blind spot.
 */
export function OmittedSection({
  projectId,
  actorName,
  clientId,
  reloadKey,
}: {
  projectId: string;
  actorName: string;
  clientId: string | null;
  reloadKey?: unknown;
}) {
  const [omitted, setOmitted] = useState<OmittedElement[] | null>(null);
  const [open, setOpen] = useState(false);
  const [family, setFamily] = useState("castillo");
  const [mark, setMark] = useState("");
  const [count, setCount] = useState("1");
  const [measure, setMeasure] = useState("");
  const [sectionCm, setSectionCm] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    getProjectReviews(projectId)
      .then((r) => setOmitted(r.omitted ?? []))
      .catch(() => setOmitted([]));
  }, [projectId]);
  useEffect(() => {
    reload();
  }, [reload, reloadKey]);

  const familyInfo = FAMILIES.find((f) => f.value === family) ?? FAMILIES[0];

  async function submit() {
    setBusy(true);
    setError(null);
    const measureValue = Number(measure.replace(",", "."));
    try {
      const result = await addOmittedElement(
        projectId,
        {
          family,
          mark: mark.trim(),
          count: Math.max(1, Number(count) || 1),
          ...(familyInfo.measure === "length" && measureValue > 0
            ? { length_m: measureValue }
            : {}),
          ...(familyInfo.measure === "area" && measureValue > 0
            ? { area_m2: measureValue }
            : {}),
          ...(sectionCm.trim() ? { section_cm: sectionCm.trim() } : {}),
          ...(note.trim() ? { note: note.trim() } : {}),
        },
        actorName,
        clientId,
      );
      setOmitted(result.omitted ?? []);
      setOpen(false);
      setMark("");
      setCount("1");
      setMeasure("");
      setSectionCm("");
      setNote("");
    } catch (e) {
      setError(
        e instanceof Error && e.message ? e.message : "No se pudo agregar el elemento.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function remove(elementId: string) {
    setBusy(true);
    try {
      const result = await removeOmittedElement(projectId, elementId, actorName, clientId);
      setOmitted(result.omitted ?? []);
    } catch {
      setError("No se pudo quitar el elemento.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mt-6 p-5">
      <SectionTitle sub="¿El motor no vio algo que está en el plano? Regístralo aquí: entra al presupuesto como levantamiento manual, con tu nombre — y le enseña al motor dónde falló.">
        Elementos omitidos por el motor
      </SectionTitle>

      {omitted && omitted.length > 0 && (
        <ul className="mb-3 space-y-1.5">
          {omitted.map((element) => (
            <li
              key={element.element_id}
              className="flex items-center gap-2 rounded-lg border border-border bg-surface-2/50 px-3 py-2 text-sm"
            >
              <span className="min-w-0 flex-1 truncate">
                <span className="font-medium">
                  {FAMILIES.find((f) => f.value === element.family)?.label ?? element.family}
                  {element.mark ? ` ${element.mark}` : ""}
                </span>{" "}
                × {element.count}
                {element.length_m ? ` · ${element.length_m} m` : ""}
                {element.area_m2 ? ` · ${element.area_m2} m²` : ""}
                {element.section_cm ? ` · ${element.section_cm} cm` : ""}
                {element.note ? ` — ${element.note}` : ""}
              </span>
              <span className="shrink-0 text-xs text-muted">{element.actor}</span>
              <button
                type="button"
                aria-label="Quitar elemento omitido"
                disabled={busy}
                onClick={() => remove(element.element_id)}
                className="shrink-0 rounded-md p-1 text-faint transition-colors hover:bg-surface-2 hover:text-danger"
              >
                <Trash size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {error && (
        <div className="mb-3">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}

      {open ? (
        <div className="space-y-3 rounded-lg border border-border bg-surface-2/40 p-4">
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="mb-1 block text-xs text-muted">Familia</span>
              <Select value={family} onChange={(e) => setFamily(e.target.value)}>
                {FAMILIES.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </Select>
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-xs text-muted">Marca (como en el plano)</span>
              <Input
                value={mark}
                onChange={(e) => setMark(e.target.value)}
                placeholder="K-7"
                className="w-28"
              />
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-xs text-muted">Cantidad</span>
              <Input
                type="number"
                min={1}
                max={500}
                value={count}
                onChange={(e) => setCount(e.target.value)}
                className="w-20"
              />
            </label>
            {familyInfo.measure !== "none" && (
              <label className="text-sm">
                <span className="mb-1 block text-xs text-muted">
                  {familyInfo.measure === "length" ? "Longitud total (m)" : "Área total (m²)"}
                </span>
                <Input
                  type="number"
                  min={0}
                  step="0.01"
                  value={measure}
                  onChange={(e) => setMeasure(e.target.value)}
                  className="w-32"
                />
              </label>
            )}
            <label className="text-sm">
              <span className="mb-1 block text-xs text-muted">Sección (cm, opcional)</span>
              <Input
                value={sectionCm}
                onChange={(e) => setSectionCm(e.target.value)}
                placeholder="15x40"
                className="w-24"
              />
            </label>
          </div>
          <label className="block text-sm">
            <span className="mb-1 block text-xs text-muted">
              Nota: dónde está y cómo lo encontraste (ayuda a mejorar la detección)
            </span>
            <Input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Eje 4-B, planta N2; el motor no leyó el símbolo"
              maxLength={300}
            />
          </label>
          <div className="flex gap-2">
            <Button
              size="sm"
              variant="primary"
              disabled={
                busy ||
                (familyInfo.measure !== "none" && !(Number(measure.replace(",", ".")) > 0))
              }
              onClick={submit}
            >
              Agregar al presupuesto
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)} disabled={busy}>
              Cancelar
            </Button>
          </div>
        </div>
      ) : (
        <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
          <PlusCircle size={15} weight="bold" /> Agregar elemento omitido
        </Button>
      )}
    </Card>
  );
}
