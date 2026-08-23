"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Trash, UploadSimple } from "@phosphor-icons/react";
import {
  ApiError,
  deleteParametricRule,
  deletePlantilla,
  getPlantillas,
  importPlantilla,
  updateParametricRule,
  type ParametricRule,
  type Plantilla,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import { Badge, Button, Card, Input, SectionTitle, Td, Th } from "@/components/ui";

const BASIS_LABEL: Record<string, string> = {
  m2_construida: "por m² construido",
  planta: "por planta",
  proyecto: "por proyecto",
};

function basisLabel(basis: string) {
  return BASIS_LABEL[basis] ?? (basis.startsWith("local:") ? `por ${basis.replace("local:", "local ")}` : basis);
}

/**
 * Plantillas: a past presupuesto plus its m² becomes per-m² rules and the
 * taller's prices; rules propose lines on new projects, marked paramétrico.
 */
export function PlantillasSection({
  onChanged,
  onError,
  onNotice,
}: {
  onChanged: () => void;
  onError: (message: string) => void;
  onNotice: (message: string) => void;
}) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [plantillas, setPlantillas] = useState<Plantilla[]>([]);
  const [rules, setRules] = useState<ParametricRule[]>([]);
  const [name, setName] = useState("");
  const [tipologia, setTipologia] = useState("");
  const [area, setArea] = useState("");
  const [busy, setBusy] = useState(false);
  const [showComparison, setShowComparison] = useState(false);

  const reload = useCallback(() => {
    getPlantillas()
      .then((r) => {
        setPlantillas(r.plantillas);
        setRules(r.rules);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function onFile(file: File) {
    const m2 = Number(area);
    if (!m2 || m2 <= 0) {
      onError("Captura los m² construidos del proyecto de la plantilla.");
      return;
    }
    setBusy(true);
    try {
      const result = await importPlantilla(
        file,
        { name: name.trim() || file.name.replace(/\.[^.]+$/, ""), tipologia: tipologia.trim(), area_m2: m2 },
        getBrowserActor(),
      );
      const problems = result.problems.length
        ? ` · ${result.problems.length} renglones sin crear (${result.problems[0]}${result.problems.length > 1 ? "…" : ""})`
        : "";
      onNotice(
        `Plantilla importada: ${result.rules} reglas por m², ${result.comparison_rules} conceptos que el motor ya lee (solo comparación), ${result.concepts_created} conceptos nuevos con su precio${problems}`,
      );
      setName("");
      setTipologia("");
      setArea("");
      reload();
      onChanged();
    } catch (e) {
      const detail =
        e instanceof ApiError && e.detail && typeof e.detail === "object"
          ? (e.detail as { message?: string }).message
          : null;
      onError(detail || "No se pudo importar la plantilla.");
    } finally {
      setBusy(false);
    }
  }

  async function removePlantilla(key: string) {
    try {
      await deletePlantilla(key, getBrowserActor());
      reload();
      onChanged();
    } catch {
      onError("No se pudo eliminar la plantilla.");
    }
  }

  async function setFactor(rule: ParametricRule, value: number) {
    if (!value || value <= 0 || value === rule.factor) return;
    try {
      await updateParametricRule(rule.id, { factor: value }, getBrowserActor());
      reload();
      onChanged();
    } catch {
      onError("No se pudo actualizar la regla.");
    }
  }

  async function toggle(rule: ParametricRule) {
    try {
      await updateParametricRule(rule.id, { active: !rule.active }, getBrowserActor());
      reload();
      onChanged();
    } catch {
      onError("No se pudo actualizar la regla.");
    }
  }

  async function removeRule(rule: ParametricRule) {
    try {
      await deleteParametricRule(rule.id, getBrowserActor());
      reload();
      onChanged();
    } catch {
      onError("No se pudo eliminar la regla.");
    }
  }

  const visible = rules.filter((r) => showComparison || !r.engine_read);
  const comparisonCount = rules.filter((r) => r.engine_read).length;
  return (
    <Card className="p-5">
      <SectionTitle sub="Un presupuesto terminado y sus m² se vuelven reglas por m²: los conceptos que el plano no lee se proponen en cada proyecto nuevo, marcados como paramétricos.">
        Plantillas y paramétricos
      </SectionTitle>
      <div className="flex flex-wrap items-center gap-2">
        <input
          ref={fileRef}
          type="file"
          accept=".csv,.xlsx"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void onFile(file);
            e.target.value = "";
          }}
        />
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Nombre (p. ej. Lote 02)"
          className="w-44 px-2 py-1.5"
          aria-label="Nombre de la plantilla"
        />
        <Input
          value={tipologia}
          onChange={(e) => setTipologia(e.target.value)}
          placeholder="Tipología (casa habitación…)"
          className="w-52 px-2 py-1.5"
          aria-label="Tipología"
        />
        <Input
          type="number"
          step="any"
          min={1}
          value={area}
          onChange={(e) => setArea(e.target.value)}
          placeholder="m² construidos"
          className="w-36 px-2 py-1.5 text-right tabular"
          aria-label="m² construidos del proyecto"
        />
        <Button onClick={() => fileRef.current?.click()} disabled={busy} variant="primary">
          <UploadSimple size={15} weight="bold" /> Importar presupuesto anterior
        </Button>
      </div>
      {plantillas.length > 0 && (
        <ul className="mt-4 divide-y divide-border">
          {plantillas.map((p) => (
            <li key={p.key} className="flex items-center gap-3 py-2 text-sm">
              <span className="font-medium">{p.name}</span>
              {p.tipologia && <Badge tone="default">{p.tipologia}</Badge>}
              <span className="tabular text-muted">{p.area_m2.toLocaleString("es-MX")} m²</span>
              <span className="text-xs text-faint">
                {p.rows} renglones · {rules.filter((r) => r.plantilla_key === p.key && !r.engine_read).length} reglas
                {p.actor && ` · ${p.actor}`}
              </span>
              <button
                type="button"
                aria-label={`Eliminar plantilla ${p.name}`}
                onClick={() => removePlantilla(p.key)}
                className="ml-auto rounded-md p-1 text-faint transition-colors hover:bg-danger-soft hover:text-danger"
              >
                <Trash size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
      {rules.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 flex items-center gap-3 text-xs text-muted">
            <span>{visible.length} reglas</span>
            {comparisonCount > 0 && (
              <button
                type="button"
                className="underline"
                onClick={() => setShowComparison((v) => !v)}
              >
                {showComparison ? "ocultar" : "mostrar"} {comparisonCount} de conceptos que el motor ya lee (solo comparación)
              </button>
            )}
          </div>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead>
                <tr className="bg-surface-2">
                  <Th>Concepto</Th>
                  <Th>Base</Th>
                  <Th align="right">Factor</Th>
                  <Th>Fuente</Th>
                  <Th>Estado</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {visible.map((r) => (
                  <tr key={r.id} className="border-t border-border">
                    <Td>
                      <span className="font-mono text-xs">{r.concept_code}</span>
                      {r.note && <span className="ml-1.5 text-xs text-faint">{r.note}</span>}
                    </Td>
                    <Td className="text-xs text-muted">{basisLabel(r.basis)}</Td>
                    <Td align="right">
                      <Input
                        type="number"
                        step="any"
                        min={0}
                        defaultValue={Number(r.factor.toFixed(4))}
                        onBlur={(e) => setFactor(r, Number(e.target.value))}
                        className="w-24 px-2 py-0.5 text-right tabular"
                        aria-label={`Factor de ${r.concept_code}`}
                      />
                    </Td>
                    <Td className="text-xs text-muted">{r.source}</Td>
                    <Td>
                      {r.engine_read ? (
                        <Badge tone="default">comparación</Badge>
                      ) : (
                        <button type="button" onClick={() => toggle(r)} className="text-xs">
                          <Badge tone={r.active ? "success" : "warning"}>
                            {r.active ? "activa" : "pausada"}
                          </Badge>
                        </button>
                      )}
                    </Td>
                    <Td>
                      <button
                        type="button"
                        aria-label="Eliminar regla"
                        onClick={() => removeRule(r)}
                        className="rounded-md p-1 text-faint transition-colors hover:bg-danger-soft hover:text-danger"
                      >
                        <Trash size={14} />
                      </button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {plantillas.length === 0 && (
        <p className="mt-3 text-xs text-faint">
          Sube el presupuesto de un proyecto terminado con sus m²: cada renglón que el plano no
          lee se vuelve una regla por m² y un concepto con su precio.
        </p>
      )}
    </Card>
  );
}
