import { UploadCloud, ScanSearch, Receipt } from "lucide-react";
import { Card } from "@/components/ui";

const STEPS = [
  {
    icon: <UploadCloud size={18} />,
    title: "Sube tu plano",
    text: "DWG o DXF estructural; la conversión y lectura corren en tu equipo.",
  },
  {
    icon: <ScanSearch size={18} />,
    title: "Detección con evidencia",
    text: "Ejes, columnas, trabes, zapatas y muros, cada uno con su origen y confianza.",
  },
  {
    icon: <Receipt size={18} />,
    title: "Presupuesto completo",
    text: "Cantidades, precios unitarios, programa de obra, flujo y riesgos revisables.",
  },
];

export function HowItWorks() {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {STEPS.map((step, i) => (
        <Card key={step.title} className="p-4">
          <div className="mb-2 flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-soft text-primary">
              {step.icon}
            </div>
            <span className="text-xs font-semibold uppercase tracking-wide text-faint">
              Paso {i + 1}
            </span>
          </div>
          <div className="font-medium">{step.title}</div>
          <p className="mt-1 text-sm leading-relaxed text-muted">{step.text}</p>
        </Card>
      ))}
    </div>
  );
}
