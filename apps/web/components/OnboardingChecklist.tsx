"use client";

import { useState } from "react";
import Link from "next/link";
import { CheckCircle, Circle, X } from "@phosphor-icons/react";
import type { WorkspaceOverview } from "@/lib/api";
import { Card, IconButton, buttonClasses } from "@/components/ui";

const DISMISS_KEY = "klave.onboarding.dismissed";

type Step = {
  key: string;
  title: string;
  why: string;
  href: string;
  linkLabel: string;
  done: boolean;
};

/**
 * The first-week path, checked against reality: each step turns green when
 * the workspace actually did it, not when someone clicked "next". Hidden
 * once everything is done, dismissable before that.
 */
export function OnboardingChecklist({
  overview,
  onExploreSample,
  sampleBusy,
}: {
  overview: WorkspaceOverview;
  onExploreSample: () => void;
  sampleBusy: boolean;
}) {
  const [dismissed, setDismissed] = useState(
    () => typeof window !== "undefined" && localStorage.getItem(DISMISS_KEY) === "1",
  );
  const onboarding = overview.onboarding;
  if (!onboarding || dismissed) return null;

  const steps: Step[] = [
    {
      key: "sample",
      title: "Explora la obra de ejemplo",
      why: "Ve un presupuesto terminado — con su evidencia y sus advertencias — antes de subir nada tuyo.",
      href: "",
      linkLabel: sampleBusy ? "Preparando…" : "Crear la obra de ejemplo",
      done: onboarding.sample_explored,
    },
    {
      key: "first",
      title: "Sube tu primer plano",
      why: "DXF abre siempre; DWG se convierte con LibreDWG. Todas las hojas de una obra juntas: se leen como un solo conjunto.",
      href: "/",
      linkLabel: "Subir un plano",
      done: onboarding.first_project,
    },
    {
      key: "verify",
      title: "Verifica una lectura",
      why: "Unidades, detecciones y supuestos: tres pasos en el Resumen. Hasta entonces, todo sale sellado SIN VERIFICAR — a propósito.",
      href: "",
      linkLabel: "Cómo funciona la verificación",
      done: onboarding.any_verified,
    },
    {
      key: "catalog",
      title: "Haz tuyo el catálogo",
      why: "Importa tus precios o adopta tus claves en el presupuesto: decides una vez y aplica a todos tus proyectos.",
      href: "/catalogo",
      linkLabel: "Abrir el catálogo",
      done: onboarding.aliases > 0,
    },
    {
      key: "deliver",
      title: "Entrega tu primer Excel",
      why: "Presupuesto → Exportar: Klave con generadores, layouts para OPUS/Neodata, catálogo de licitación con P.U. con letra.",
      href: "",
      linkLabel: "Ver la guía de entrega",
      done: onboarding.any_exported,
    },
  ];
  const remaining = steps.filter((s) => !s.done).length;
  if (remaining === 0) return null;

  function dismiss() {
    localStorage.setItem(DISMISS_KEY, "1");
    setDismissed(true);
  }

  return (
    <Card className="mb-6 p-5">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="font-medium">Empieza aquí</div>
          <p className="text-sm text-muted">
            Cinco pasos del plano a la entrega; cada uno se marca solo cuando de verdad
            ocurrió.{" "}
            <Link href="/como-funciona" className="underline">
              Por qué la app trabaja así
            </Link>
            .
          </p>
        </div>
        <IconButton aria-label="No mostrar más esta guía" onClick={dismiss}>
          <X size={15} />
        </IconButton>
      </div>
      <ol className="space-y-2">
        {steps.map((step, index) => (
          <li key={step.key} className="flex items-start gap-3 rounded-lg px-2 py-2 hover:bg-surface-2/50">
            {step.done ? (
              <CheckCircle size={20} weight="fill" className="mt-0.5 shrink-0 text-success" />
            ) : (
              <Circle size={20} className="mt-0.5 shrink-0 text-faint" />
            )}
            <div className="min-w-0 flex-1">
              <div className={`text-sm font-medium ${step.done ? "text-muted line-through" : ""}`}>
                {index + 1}. {step.title}
              </div>
              {!step.done && <p className="text-sm text-muted">{step.why}</p>}
            </div>
            {!step.done && (
              <span className="shrink-0">
                {step.key === "sample" ? (
                  <button
                    type="button"
                    onClick={onExploreSample}
                    disabled={sampleBusy}
                    className={buttonClasses("secondary", "sm")}
                  >
                    {step.linkLabel}
                  </button>
                ) : step.key === "verify" || step.key === "deliver" ? (
                  <Link href="/como-funciona" className={buttonClasses("ghost", "sm")}>
                    {step.linkLabel}
                  </Link>
                ) : (
                  <Link href={step.href} className={buttonClasses("ghost", "sm")}>
                    {step.linkLabel}
                  </Link>
                )}
              </span>
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
}
