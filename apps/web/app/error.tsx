"use client";

import Link from "next/link";
import { ArrowLeft, CircleAlert, RotateCcw } from "lucide-react";

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
        <CircleAlert size={22} />
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
        <button
          type="button"
          onClick={reset}
          className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-fg transition hover:bg-primary-hover"
        >
          <RotateCcw size={15} /> Reintentar
        </button>
        <Link
          href="/"
          className="inline-flex items-center gap-2 rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium shadow-sm transition hover:bg-surface-2"
        >
          <ArrowLeft size={15} /> Proyectos
        </Link>
      </div>
    </div>
  );
}
