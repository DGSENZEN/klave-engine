"use client";

import { useState } from "react";
import Link from "next/link";
import { CheckCircle, Circle, Question } from "@phosphor-icons/react";
import { reiniciarObraDeEjemplo } from "@/lib/api";
import { CAPITULOS } from "@/lib/recorrido/capitulos";
import { empezarDeCero } from "@/lib/recorrido/reinicio";
import {
  abrirMenuRecorrido,
  almacen,
  capituloHecho,
  capituloPendiente,
  despachar,
  iniciarCapitulo,
  useMenuRecorrido,
  useRecorrido,
} from "@/lib/recorridoStore";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Modal } from "@/components/Modal";
import { Button, Callout, iconButtonClasses } from "@/components/ui";

/** El «?» de un encabezado: abre el menú del recorrido. */
export function BotonRecorrido({ ancla }: { ancla: string }) {
  return (
    <button
      type="button"
      data-tour={ancla}
      aria-label="Recorrido guiado"
      data-tip="Recorrido guiado"
      onClick={() => abrirMenuRecorrido()}
      className={iconButtonClasses()}
    >
      <Question />
    </button>
  );
}

/** Capítulos con su avance, continuar, repasar uno, o empezar de cero. */
export function DialogoRecorrido() {
  const abierto = useMenuRecorrido();
  const estado = useRecorrido();
  const [confirmar, setConfirmar] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const pendiente = capituloPendiente(estado.progreso);
  const cerrar = () => abrirMenuRecorrido(false);

  function ir(id: (typeof CAPITULOS)[number]["id"]) {
    cerrar();
    iniciarCapitulo(id);
  }

  async function deCero() {
    setConfirmar(false);
    const resultado = await empezarDeCero(estado.projectId, {
      reiniciar: reiniciarObraDeEjemplo,
      borrar: () => almacen.borrar(),
    });
    if (!resultado.ok) {
      // La obra no volvió a la Rev A: el progreso se queda y se dice por qué.
      setAviso(resultado.mensaje);
      return;
    }
    setAviso(null);
    cerrar();
    despachar({ tipo: "progreso", progreso: {} });
    iniciarCapitulo("arranque");
  }

  return (
    <>
      <Modal
        open={abierto && !confirmar}
        title="Recorrido guiado"
        sub="Del plano al Excel, en tu propia obra de ejemplo. Cada capítulo se puede repasar."
        onClose={cerrar}
        footer={
          <div className="flex w-full flex-wrap items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setConfirmar(true)}>
              Empezar de cero con la obra
            </Button>
            <span className="ml-auto" />
            {pendiente && (
              <Button variant="primary" size="sm" onClick={() => ir(pendiente)}>
                {Object.keys(estado.progreso).length ? "Continuar" : "Empezar"}
              </Button>
            )}
          </div>
        }
      >
        {aviso && (
          <div className="mb-3">
            <Callout tone="warning">{aviso}</Callout>
          </div>
        )}
        <ol className="space-y-1">
          {CAPITULOS.map((capitulo, i) => {
            const hecho = capituloHecho(capitulo.id, estado.progreso);
            return (
              <li key={capitulo.id}>
                <button
                  type="button"
                  onClick={() => ir(capitulo.id)}
                  className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-surface-2"
                >
                  {hecho ? (
                    <CheckCircle weight="fill" className="shrink-0 text-success" />
                  ) : (
                    <Circle className="shrink-0 text-faint" />
                  )}
                  <span className="flex-1 text-sm font-medium">
                    {i}. {capitulo.titulo}
                  </span>
                  <span className="text-xs tabular-nums text-faint">{capitulo.minutos} min</span>
                </button>
              </li>
            );
          })}
        </ol>
        <p className="mt-4 text-xs text-faint">
          ¿Un término no te suena? Está en el{" "}
          <Link href="/glosario" className="underline" onClick={cerrar}>
            glosario
          </Link>
          . Las reglas que la app no rompe, en{" "}
          <Link href="/como-funciona" className="underline" onClick={cerrar}>
            cómo funciona
          </Link>
          .
        </p>
      </Modal>
      <ConfirmDialog
        open={confirmar}
        title="¿Empezar de cero con la obra de ejemplo?"
        description="Tu obra de ejemplo vuelve a la Rev A, sin tus revisiones ni tus mapeos, y el recorrido empieza otra vez desde el arranque. Tus obras reales no cambian."
        confirmLabel="Empezar de cero"
        onConfirm={() => void deCero()}
        onCancel={() => setConfirmar(false)}
      />
    </>
  );
}
