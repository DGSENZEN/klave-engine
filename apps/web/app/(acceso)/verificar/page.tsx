"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CheckCircle } from "@phosphor-icons/react";
import { apiMessage, confirmVerification } from "@/lib/session";
import { AuthFrame, useQueryParam } from "@/components/AuthFrame";
import { buttonClasses, Callout, Skeleton } from "@/components/ui";

type State =
  | { kind: "loading" }
  | { kind: "done"; email: string; changed: boolean }
  | { kind: "error"; message: string };

export default function VerificarPage() {
  const token = useQueryParam("token");
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    if (token === undefined) return;
    if (!token) {
      const handle = window.setTimeout(
        () => setState({ kind: "error", message: "Falta el código de confirmación." }),
        0,
      );
      return () => window.clearTimeout(handle);
    }
    let active = true;
    confirmVerification(token)
      .then((r) => active && setState({ kind: "done", email: r.email, changed: r.changed }))
      .catch((e) => {
        if (active) {
          setState({
            kind: "error",
            message: apiMessage(e, "El enlace de confirmación ya no es válido."),
          });
        }
      });
    return () => {
      active = false;
    };
  }, [token]);

  return (
    <AuthFrame title="Confirmar correo">
      {state.kind === "loading" ? (
        <div>
          <Skeleton className="h-4 w-40" />
          <Skeleton className="mt-3 h-9" />
        </div>
      ) : state.kind === "error" ? (
        <div>
          <Callout tone="danger">{state.message}</Callout>
          <Link href="/cuenta" className={buttonClasses("secondary", "lg", "mt-4 w-full")}>
            Ir a mi cuenta
          </Link>
        </div>
      ) : (
        <div>
          <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-success-soft text-success">
            <CheckCircle size={24} weight="duotone" />
          </div>
          <p className="font-medium">Correo confirmado</p>
          <p className="mt-1 text-sm text-muted">
            {state.changed
              ? `Desde ahora entras con ${state.email}.`
              : `${state.email} queda verificado en tu cuenta.`}
          </p>
          <Link href="/" className={buttonClasses("primary", "lg", "mt-6 w-full")}>
            Ir a los proyectos
          </Link>
        </div>
      )}
    </AuthFrame>
  );
}
