"use client";

import { useState, useSyncExternalStore } from "react";
import { CheckCircle, Circle, Compass, X } from "@phosphor-icons/react";
import { CAPITULOS } from "@/lib/recorrido/capitulos";
import {
  capituloHecho,
  capituloPendiente,
  iniciarCapitulo,
  useRecorrido,
} from "@/lib/recorridoStore";
import { Button, IconButton } from "@/components/ui";

const DESPUES = "klave.recorrido.despues";
const sinCambios = () => () => {};

function leerDespues(): boolean {
  try {
    return window.localStorage.getItem(DESPUES) === "1";
  } catch {
    return false;
  }
}

/** La entrada al recorrido en la página principal. Desaparece al terminarlo;
 * «Más tarde» la esconde (el «?» de arriba sigue a la mano). */
export function InicioRecorrido() {
  const estado = useRecorrido();
  // Sólo en el cliente: el servidor no sabe si la persona dijo «más tarde».
  const enCliente = useSyncExternalStore(sinCambios, () => true, () => false);
  const [ocultaAhora, setOcultaAhora] = useState(false);
  const despues = ocultaAhora || (enCliente && leerDespues());
  const pendiente = capituloPendiente(estado.progreso);
  const empezado = Object.keys(estado.progreso).length > 0;
  if (!enCliente || !pendiente || despues || CAPITULOS.length === 0) return null;
  const minutos = CAPITULOS.reduce((total, c) => total + c.minutos, 0);

  function masTarde() {
    try {
      window.localStorage.setItem(DESPUES, "1");
    } catch {
      // sin almacenamiento: se esconde sólo en esta visita
    }
    setOcultaAhora(true);
  }

  return (
    <div className="card mb-6 p-5" data-tour="inicio.recorrido">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-2">
          <Compass size={20} weight="duotone" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-medium">Recorrido guiado · ~{minutos} min</div>
          <p className="text-sm text-muted">
            Haz una obra completa, del plano al Excel para OPUS, en una obra de ejemplo tuya.
            Cada paso lo haces tú, en la pantalla real.
          </p>
        </div>
        <IconButton aria-label="Más tarde" onClick={masTarde}>
          <X size={15} />
        </IconButton>
      </div>
      {empezado && (
        <ol className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
          {CAPITULOS.map((capitulo) => (
            <li key={capitulo.id} className="flex items-center gap-1.5 text-xs text-muted">
              {capituloHecho(capitulo.id, estado.progreso) ? (
                <CheckCircle size={14} weight="fill" className="text-success" />
              ) : (
                <Circle size={14} className="text-faint" />
              )}
              {capitulo.titulo}
            </li>
          ))}
        </ol>
      )}
      <div className="mt-4 flex gap-2">
        <Button variant="primary" size="sm" onClick={() => iniciarCapitulo(pendiente)}>
          {empezado ? "Continuar" : "Empezar"}
        </Button>
        {!empezado && (
          <Button variant="ghost" size="sm" onClick={masTarde}>
            Más tarde
          </Button>
        )}
      </div>
    </div>
  );
}
