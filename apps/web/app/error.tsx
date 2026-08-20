"use client";

import Link from "next/link";
import { ArrowLeft, ArrowCounterClockwise, WarningCircle } from "@phosphor-icons/react";
import { buttonClasses } from "@/components/ui";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center px-6 text-center">
      <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-full bg-danger-soft text-danger">
        <WarningCircle size={22} weight="duotone" />
      </div>
      <h1 className="text-xl font-semibold">Algo salió mal</h1>
      <p className="mt-2 text-sm text-muted">
        Ocurrió un error inesperado en la interfaz. Puedes reintentar o volver a la lista
        de proyectos.
      </p>
      {error.digest && (
        <p className="mt-2 font-mono text-xs text-faint">ref: {error.digest}</p>
      )}
      <div className="mt-6 flex items-center gap-2">
        <button type="button" onClick={reset} className={buttonClasses("primary")}>
          <ArrowCounterClockwise size={15} weight="bold" /> Reintentar
        </button>
        <Link href="/" className={buttonClasses("secondary")}>
          <ArrowLeft size={15} weight="bold" /> Proyectos
        </Link>
      </div>
    </div>
  );
}
