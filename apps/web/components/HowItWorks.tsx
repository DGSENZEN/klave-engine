"use client";

import { CloudArrowUp, Scan, Receipt } from "@phosphor-icons/react";
import { Card } from "@/components/ui";

const STEPS = [
  {
    icon: <CloudArrowUp size={20} weight="duotone" />,
    title: "Sube tu plano",
    text: "DWG o DXF estructural; la conversión y lectura corren en tu equipo.",
  },
  {
    icon: <Scan size={20} weight="duotone" />,
    title: "Detección con evidencia",
    text: "Ejes, columnas, trabes, zapatas y muros, cada uno con su origen y confianza.",
  },
  {
    icon: <Receipt size={20} weight="duotone" />,
    title: "Presupuesto completo",
    text: "Cantidades, precios unitarios, programa de obra, flujo y riesgos revisables.",
  },
];

export function HowItWorks() {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {STEPS.map((step, i) => (
        <Card key={step.title} className="p-4">
          <div className="mb-2.5 flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-2 text-foreground">
              {step.icon}
            </div>
            <span className="microlabel">Paso {i + 1}</span>
          </div>
          <div className="font-medium">{step.title}</div>
          <p className="mt-1 text-sm leading-relaxed text-muted">{step.text}</p>
        </Card>
      ))}
    </div>
  );
}
