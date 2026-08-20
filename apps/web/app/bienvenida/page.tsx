"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Buildings, Monitor } from "@phosphor-icons/react";
import { peekBrowserActor } from "@/lib/collab";
import { completeProfile } from "@/lib/identity";
import { HowItWorks } from "@/components/HowItWorks";
import { buttonClasses, Card, Input } from "@/components/ui";
import { ThemeToggle } from "@/components/ThemeToggle";

/**
 * First-run onboarding: establishes the workspace identity used to attribute
 * cambios, presencia y actividad. In the hosted deployment this screen becomes
 * the OIDC login step; the local flow deliberately avoids fake credentials.
 */
export default function BienvenidaPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [touched, setTouched] = useState(false);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setName(peekBrowserActor());
    }, 0);
    return () => window.clearTimeout(handle);
  }, []);

  const valid = name.trim().length >= 2;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (!valid) return;
    completeProfile(name);
    router.replace("/");
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center px-5 py-10 sm:px-6">
      <div className="rise-in">
        <div className="mb-8 flex items-start justify-between gap-4">
          <div className="flex items-center gap-3.5">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-primary-fg">
              <Buildings size={22} weight="duotone" />
            </div>
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">Bienvenido a Klave</h1>
              <p className="text-sm text-muted">
                Ingeniería de costos a partir de planos estructurales.
              </p>
            </div>
          </div>
          <ThemeToggle />
        </div>

        <Card className="mb-6 p-6">
          <form onSubmit={onSubmit}>
            <label htmlFor="nombre" className="mb-1.5 block text-sm font-medium">
              ¿Cómo te llamas?
            </label>
            <p className="mb-3 text-sm text-muted">
              Tu nombre identifica tus cambios y tu presencia cuando colaboras en un
              proyecto.
            </p>
            <div className="flex flex-col gap-3 sm:flex-row">
              <Input
                id="nombre"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Nombre y apellido"
                autoFocus
                maxLength={40}
                className="flex-1"
              />
              <button
                type="submit"
                className={buttonClasses("primary")}
                disabled={touched && !valid}
              >
                Comenzar <ArrowRight size={15} weight="bold" />
              </button>
            </div>
            {touched && !valid && (
              <p className="mt-2 text-sm text-danger">
                Escribe un nombre de al menos 2 caracteres.
              </p>
            )}
          </form>
        </Card>

        <HowItWorks />

        <p className="mt-6 flex items-center gap-2 text-xs text-faint">
          <Monitor size={14} />
          Modo local: tus planos y presupuestos se procesan y guardan en tu equipo.
        </p>
      </div>
    </div>
  );
}
