"use client";

import Link from "next/link";
import { ArrowLeft, Buildings, Question } from "@phosphor-icons/react";
import { buttonClasses } from "@/components/ui";

export default function NotFound() {
  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center px-6 text-center">
      <div className="mb-6 flex h-12 w-12 items-center justify-center rounded-full bg-surface-2 text-muted">
        <Question size={22} weight="duotone" />
      </div>
      <h1 className="text-xl font-semibold">Página no encontrada</h1>
      <p className="mt-2 text-sm text-muted">
        La página que buscas no existe o el proyecto fue eliminado.
      </p>
      <Link href="/" className={buttonClasses("primary", "md", "mt-6")}>
        <ArrowLeft size={15} weight="bold" /> Ir a proyectos
      </Link>
      <div className="mt-10 flex items-center gap-1.5 text-xs text-faint">
        <Buildings size={13} weight="duotone" /> Klave
      </div>
    </div>
  );
}
