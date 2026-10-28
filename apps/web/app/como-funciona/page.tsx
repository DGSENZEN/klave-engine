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
      "Cada cantidad apunta al elemento del que salió: qué marca, en qué hoja, con qué medida. Si Klave supuso algo (un vano típico, una altura), el supuesto está escrito junto al número. Nunca vas a encontrar una cantidad que no puedas rastrear hasta un trazo del dibujo o un supuesto declarado.",
  },
  {
    icon: <Prohibit size={20} weight="duotone" />,
    title: "Lo que no se sabe, no se inventa",
    body:
      "Un plano sin unidades confiables sale marcado SIN UNIDADES y sin precios — no con precios equivocados. Un insumo sin precio aparece como «sin precio», jamás como $0. Un total que esconde huecos es peor que un total incompleto que los enseña.",
  },
  {
    icon: <SealCheck size={20} weight="duotone" />,
    title: "El dinero pasa por tu firma",
    body:
      "Pantallas y Excel llevan el sello SIN VERIFICAR hasta que confirmas tres cosas en el Resumen: las unidades del dibujo, las detecciones (con sus exclusiones) y los supuestos. La app propone; el perito dispone. Un presupuesto sin verificar no se entrega.",
  },
  {
    icon: <Scales size={20} weight="duotone" />,
    title: "Cada precio dice de dónde viene",
    body:
      "Referencia de Klave, cotización de tu proveedor, publicación oficial (CDMX, SICT) o calculado (salario real RLOPSRM, costo horario, índice). La vigencia también: vigente, por revisar o vencido. Los precios de referencia son punto de partida, no «precios de mercado» — esos los pones tú.",
  },
  {
    icon: <Eye size={20} weight="duotone" />,
    title: "La IA sugiere, nunca decide",
    body:
      "Si el servidor tiene credenciales, un modelo de visión lee las hojas y completa lo que las reglas no alcanzaron (una sección, un armado). Cada lectura queda marcada «por confirmar» con su procedencia. La IA jamás cuantifica ni pone un precio por sí sola.",
  },
  {
    icon: <FileXls size={20} weight="duotone" />,
    title: "La entrega es tuya, con tu catálogo",
    body:
      "El Excel sale con generadores y croquis para defender cada número, en el layout de Klave o en los que importan OPUS y Neodata. Si adoptaste tus claves y precios en el catálogo, el presupuesto habla el idioma de tu taller, no el nuestro.",
  },
];

export default function ComoFuncionaPage() {
  return (
    <div className="min-h-screen">
      <WorkspaceHeader active={null} />
      <main className="mx-auto max-w-6xl px-5 py-8 sm:px-6 *:max-w-3xl">
        <PageHeader
          title="Cómo funciona — y por qué así"
          sub="Klave convierte planos DWG/DXF en presupuestos de obra. Estas son las reglas que la app no rompe, porque un presupuesto vale lo que vale su evidencia."
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
          ¿Términos nuevos? El{" "}
          <Link href="/glosario" className="font-medium text-foreground underline">
            glosario
          </Link>{" "}
          explica cada uno. Para aprender el camino haciéndolo, abre el recorrido guiado
          desde Ayuda, arriba: una obra de ejemplo tuya, del plano al Excel.
        </p>
      </main>
    </div>
  );
}
