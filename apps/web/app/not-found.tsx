import Link from "next/link";
import { ArrowLeft, Building2, FileQuestion } from "lucide-react";

export default function NotFound() {
  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center px-6 text-center">
      <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-full bg-surface-2 text-muted">
        <FileQuestion size={22} />
      </div>
      <h1 className="text-xl font-semibold">Página no encontrada</h1>
      <p className="mt-2 text-sm text-muted">
        La página que buscas no existe o el proyecto fue eliminado.
      </p>
      <Link
        href="/"
        className="mt-6 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-fg transition hover:bg-primary-hover"
      >
        <ArrowLeft size={15} /> Ir a proyectos
      </Link>
      <div className="mt-10 flex items-center gap-1.5 text-xs text-faint">
        <Building2 size={13} /> Klave
      </div>
    </div>
  );
}
