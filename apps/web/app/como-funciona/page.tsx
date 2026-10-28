"use client";

import Link from "next/link";
import {
  Eye,
  FileXls,
  MagnifyingGlass,
  Prohibit,
  Scales,
  SealCheck,
} from "@phosphor-icons/react";
import { WorkspaceHeader } from "@/components/WorkspaceHeader";
import { Card, PageHeader } from "@/components/ui";

/** The "why" behind the product: not a feature tour, the rules the app
 * refuses to break. Each principle names what would go wrong without it. */
const PRINCIPLES: {
  icon: React.ReactNode;
  title: string;
  body: string;
}[] = [
  {
    icon: <MagnifyingGlass size={20} weight="duotone" />,
    title: "Todo sale del plano, con evidencia",
    body:
      "Cada cantidad apunta al elemento del que salió: qué marca, en qué hoja, con qué medida. Si Klave supuso algo (un vano típico, una altura), el supuesto está escrito junto al número. Toda cantidad se rastrea hasta un trazo del dibujo o un supuesto declarado.",
  },
  {
    icon: <Prohibit size={20} weight="duotone" />,
    title: "Lo que falta queda a la vista",
    body:
      "Un plano sin unidades confiables sale marcado SIN UNIDADES y sin precios. Un insumo sin precio aparece como «sin precio». Un total incompleto muestra qué le falta.",
  },
  {
    icon: <SealCheck size={20} weight="duotone" />,
    title: "El dinero pasa por tu firma",
    body:
      "Pantallas y Excel llevan el sello SIN VERIFICAR hasta que confirmas tres cosas en el Resumen: las unidades del dibujo, las detecciones (con sus exclusiones) y los supuestos. Un presupuesto sin verificar no se entrega.",
  },
  {
    icon: <Scales size={20} weight="duotone" />,
    title: "Cada precio dice de dónde viene",
    body:
      "Cada precio lleva su procedencia: referencia de Klave, cotización de tu proveedor, publicación oficial (CDMX, SICT) o calculado (salario real RLOPSRM, costo horario, índice). También lleva su vigencia: vigente, por revisar o vencido. Los precios de referencia son un punto de partida; los precios de mercado los pones tú.",
  },
  {
    icon: <Eye size={20} weight="duotone" />,
    title: "La IA sugiere; tú decides",
    body:
      "Si el servidor tiene credenciales, un modelo de visión lee las hojas y completa lo que las reglas no alcanzaron (una sección, un armado). Cada lectura queda marcada «por confirmar» con su procedencia. La IA no cuantifica ni pone precios por sí sola.",
  },
  {
    icon: <FileXls size={20} weight="duotone" />,
    title: "La entrega es tuya, con tu catálogo",
    body:
      "El Excel sale con generadores y croquis para defender cada número, en el layout de Klave o en los que importan OPUS y Neodata. Si adoptaste tus claves y precios en el catálogo, el presupuesto sale con ellos.",
  },
];

export default function ComoFuncionaPage() {
  return (
    <div className="min-h-screen">
      <WorkspaceHeader active={null} />
      <main className="mx-auto max-w-3xl px-5 py-8 sm:px-6">
        <PageHeader
          title="Cómo funciona y por qué"
          sub="Klave convierte planos DWG/DXF en presupuestos de obra. Estas son las reglas que la app siempre cumple, porque un presupuesto vale lo que vale su evidencia."
        />

        <div className="space-y-4">
          {PRINCIPLES.map((principle) => (
            <Card key={principle.title} className="p-5">
              <div className="mb-1.5 flex items-center gap-2.5">
                <span className="text-accent">{principle.icon}</span>
                <h2 className="font-medium">{principle.title}</h2>
              </div>
              <p className="text-sm text-muted">{principle.body}</p>
            </Card>
          ))}
        </div>

        <p className="mt-8 text-sm text-muted">
          El{" "}
          <Link href="/glosario" className="font-medium text-foreground underline">
            glosario
          </Link>{" "}
          explica cada término. Para aprender haciendo, abre el recorrido guiado desde
          Ayuda, arriba: lleva una obra de ejemplo tuya del plano al Excel.
        </p>
      </main>
    </div>
  );
}
