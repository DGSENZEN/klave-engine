"use client";

import { WorkspaceHeader } from "@/components/WorkspaceHeader";
import { Card, PageHeader, SectionTitle } from "@/components/ui";

const SECTIONS: { title: string; terms: [string, string][] }[] = [
  {
    title: "Del plano a la cantidad",
    terms: [
      ["Detección", "Un elemento que el motor leyó del plano (un castillo, una trabe, un muro), con la evidencia de dónde y cómo lo leyó."],
      ["Marca", "La etiqueta tal como está dibujada (K-1, T-2, Z-3). Nunca se reescribe: es la fuente de verdad."],
      ["Confianza", "Qué tan seguro está el motor de una lectura: ≥ 70 % firme, 45–70 % duda por revisar, menos es débil."],
      ["Unidades de dibujo", "Las coordenadas crudas del archivo. Sin una unidad confiable (metros, centímetros…) las cantidades no se convierten y nada lleva precio."],
      ["Generador", "El desglose de dónde salió cada cantidad: qué elementos, en qué planta, con qué supuesto."],
      ["Paramétrico", "Una cantidad propuesta desde la historia del taller (por m², por planta, por local), no leída del plano. Siempre se marca."],
      ["Vano", "Puerta o ventana descontada de un muro: medida cuando el plano la dibuja, supuesta (y declarada) cuando no."],
    ],
  },
  {
    title: "Del concepto al precio",
    terms: [
      ["Concepto", "Una partida de obra con clave, unidad y descripción (EST-001, Columnas y castillos…)."],
      ["P.U. — precio unitario", "Lo que cuesta una unidad del concepto. Directo (sin indirectos) dentro del análisis; con sobrecosto en el catálogo de licitación."],
      ["APU / matriz", "El análisis del P.U.: cuánto material, mano de obra y equipo consume una unidad del concepto, con rendimientos."],
      ["Insumo", "Un recurso comprable: cemento, un albañil por jornada, una revolvedora por hora."],
      ["%MO — herramienta menor", "La herramienta de mano se cobra como porcentaje de la mano de obra de la matriz, como se estila en México."],
      ["Explosión de insumos", "APU × cantidad, sumado por insumo: lo que hay que comprar, contratar y programar."],
      ["Vigencia", "La fecha del precio. Vigente hasta 6 meses, por revisar hasta 12, vencido después; los vencidos se cotizan o se traen por índice."],
      ["Referencia / cotización / publicación / calculado", "La procedencia de cada precio: semilla de Klave, precio del proveedor, tabulador oficial, o derivado (salario real, índice)."],
      ["Clave del taller (alias)", "Tu clave, descripción y precio para un concepto de Klave: el presupuesto sale con tu catálogo."],
    ],
  },
  {
    title: "Salario real (RLOPSRM art. 190–191)",
    terms: [
      ["Sn — salario nominal", "Lo que se paga por día de trabajo, antes de prestaciones."],
      ["SBC — salario base de cotización", "El salario con prestaciones mínimas de ley, base de las cuotas IMSS."],
      ["Ps — prestaciones", "Cuotas patronales IMSS, INFONAVIT e impuesto sobre nómina, por día."],
      ["Tp / Tl", "Días pagados al año / días realmente laborados. Su cociente encarece cada día trabajado."],
      ["Fsr — factor de salario real", "Ps × (Tp/Tl): el multiplicador del salario nominal. El costo real de un jornal."],
      ["Costo horario", "El precio por hora de una máquina según el reglamento: cargos fijos + consumos + operación (arts. 194–206)."],
    ],
  },
  {
    title: "Entrega",
    terms: [
      ["LOPSRM", "Ley de Obras Públicas y Servicios Relacionados con las Mismas: rige la obra pública; su reglamento (RLOPSRM) define salario real y costo horario."],
      ["Catálogo de licitación", "El formato de entrega para concurso: partidas numeradas, P.U. con número y letra, importes."],
      ["P.U.O.T.", "\"Precio Unitario por Obra Terminada\": la descripción larga termina así por convención."],
      ["OPUS / Neodata", "Los programas de precios unitarios más usados en México. Klave exporta layouts de Excel que ambos importan."],
      ["SIN VERIFICAR", "El sello que llevan pantallas y Excel hasta que alguien confirma unidades y detecciones. El dinero sin verificar no se entrega."],
    ],
  },
];

export default function GlosarioPage() {
  return (
    <div className="min-h-screen">
      <WorkspaceHeader active={null} />
      <main className="mx-auto max-w-3xl px-5 py-8 sm:px-6">
        <PageHeader
          title="Glosario"
          sub="Los términos que la aplicación usa, en el orden en que aparecen: del plano a la cantidad, de la cantidad al precio, del precio a la entrega."
        />
        <div className="space-y-4">
          {SECTIONS.map((section) => (
            <Card key={section.title} className="p-5">
              <SectionTitle>{section.title}</SectionTitle>
              <dl className="space-y-3">
                {section.terms.map(([term, definition]) => (
                  <div key={term}>
                    <dt className="text-sm font-medium">{term}</dt>
                    <dd className="text-sm text-muted">{definition}</dd>
                  </div>
                ))}
              </dl>
            </Card>
          ))}
        </div>
      </main>
    </div>
  );
}
