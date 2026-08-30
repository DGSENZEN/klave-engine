"use client";

import { useEffect, useState } from "react";
import { usePathname, useParams } from "next/navigation";
import { Sparkle } from "@phosphor-icons/react";
import { getAcciones } from "@/lib/api";
import { Copilot } from "@/components/Copilot";

/**
 * El copiloto, siempre a la mano.
 *
 * Flota abajo a la derecha en todas las pantallas de trabajo — no en las de
 * acceso, donde no hay proyecto ni sesión y solo estorbaría. Cuando la obra
 * abierta tiene algo que Klave puede hacer, el botón lo dice con un número:
 * la ayuda va a buscar al usuario en lugar de esperar a que se acuerde de
 * abrirla, que es la diferencia entre una herramienta y un adorno.
 */

// Pantallas de acceso y recuperación: ahí no hay nada que copilotear.
const SIN_COPILOTO = [
  "/bienvenida",
  "/invitacion",
  "/recuperar",
  "/restablecer",
  "/verificar",
];

export function CopilotFab() {
  const pathname = usePathname() ?? "";
  const params = useParams<{ id?: string }>();
  const projectId = typeof params?.id === "string" ? params.id : undefined;
  const [open, setOpen] = useState(false);
  // El conteo recuerda de qué obra es: así el número de un proyecto nunca
  // aparece un instante sobre otro al navegar entre ellos.
  const [conteo, setConteo] = useState<{ id: string; n: number } | null>(null);

  useEffect(() => {
    if (!projectId) return;
    let vivo = true;
    getAcciones(projectId)
      .then((r) => {
        if (vivo) {
          setConteo({ id: projectId, n: r.acciones.filter((a) => a.aplicable).length });
        }
      })
      .catch(() => {
        if (vivo) setConteo({ id: projectId, n: 0 });
      });
    return () => {
      vivo = false;
    };
  }, [projectId, pathname, open]);

  const pendientes = projectId && conteo?.id === projectId ? conteo.n : 0;

  if (SIN_COPILOTO.some((ruta) => pathname.startsWith(ruta))) return null;

  return (
    <>
      {/* Con el cajón abierto el botón estorbaría justo encima del campo de
          escritura, y el cajón ya trae su propia salida. */}
      {!open && (
      <button
        type="button"
        data-copiloto-boton
        onClick={() => setOpen(true)}
        aria-label={
          pendientes > 0
            ? `Pregúntale a Klave — ${pendientes} cosa(s) que puede hacer`
            : "Pregúntale a Klave"
        }
        className="toast-in fixed bottom-5 right-5 z-[60] flex h-12 w-12 items-center justify-center rounded-full bg-primary text-primary-fg shadow-lg transition hover:scale-105 hover:brightness-110 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <Sparkle size={20} weight="duotone" />
        {pendientes > 0 && (
          <span
            className="tabular absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-accent px-1.5 text-xs font-semibold text-white shadow-sm"
            aria-hidden
          >
            {pendientes}
          </span>
        )}
      </button>
      )}
      <Copilot open={open} onClose={() => setOpen(false)} />
    </>
  );
}
