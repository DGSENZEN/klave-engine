"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Buildings, GoogleLogo, Monitor, SignOut } from "@phosphor-icons/react";
import { peekBrowserActor } from "@/lib/collab";
import { completeProfile } from "@/lib/identity";
import { fetchAuthStatus, logout, type AuthStatus } from "@/lib/session";
import { HowItWorks } from "@/components/HowItWorks";
import { Avatar, buttonClasses, Callout, Card, Input, Skeleton } from "@/components/ui";
import { ThemeToggle } from "@/components/ThemeToggle";

/**
 * First-run onboarding and sign-in. With Google credentials configured the
 * primary path is "Continuar con Google"; the local display-name flow stays
 * available so the tool never depends on external credentials to work.
 */
export default function BienvenidaPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [touched, setTouched] = useState(false);
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [googleError, setGoogleError] = useState(false);

  useEffect(() => {
    let active = true;
    const failedGoogle =
      new URLSearchParams(window.location.search).get("error") === "google";
    const handle = window.setTimeout(() => {
      if (active && failedGoogle) setGoogleError(true);
    }, 0);
    fetchAuthStatus().then((status) => {
      if (!active) return;
      setAuth(status);
      setName((current) => current || status.user?.name || peekBrowserActor());
    });
    return () => {
      active = false;
      window.clearTimeout(handle);
    };
  }, []);

  const valid = name.trim().length >= 2;

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (!valid) return;
    completeProfile(name);
    router.replace("/");
  }

  async function onLogout() {
    await logout();
    const status = await fetchAuthStatus();
    setAuth(status);
    setName(peekBrowserActor());
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

        {googleError && (
          <div className="mb-4">
            <Callout tone="danger">
              No se pudo iniciar sesión con Google. Inténtalo de nuevo o continúa con tu
              nombre.
            </Callout>
          </div>
        )}

        <Card className="mb-6 p-6">
          {auth === null ? (
            <div>
              <Skeleton className="h-4 w-40" />
              <Skeleton className="mt-3 h-9" />
            </div>
          ) : auth.user ? (
            <div>
              <div className="mb-4 flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  <Avatar name={auth.user.name} src={auth.user.picture} self />
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{auth.user.name}</div>
                    <div className="truncate text-xs text-muted">{auth.user.email}</div>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={onLogout}
                  className={buttonClasses("ghost", "sm")}
                >
                  <SignOut size={14} weight="bold" /> Cerrar sesión
                </button>
              </div>
              <form onSubmit={onSubmit}>
                <label htmlFor="nombre" className="mb-1.5 block text-sm font-medium">
                  Nombre visible en el proyecto
                </label>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <Input
                    id="nombre"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    maxLength={40}
                    className="flex-1"
                  />
                  <button
                    type="submit"
                    className={buttonClasses("primary")}
                    disabled={touched && !valid}
                  >
                    Continuar <ArrowRight size={15} weight="bold" />
                  </button>
                </div>
              </form>
            </div>
          ) : (
            <div>
              {auth.enabled && (
                <>
                  <a href="/api/auth/google" className={buttonClasses("primary", "md", "w-full")}>
                    <GoogleLogo size={16} weight="bold" /> Continuar con Google
                  </a>
                  <div className="my-5 flex items-center gap-3 text-xs text-faint">
                    <span className="h-px flex-1 bg-border" />
                    o con tu nombre
                    <span className="h-px flex-1 bg-border" />
                  </div>
                </>
              )}
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
                    autoFocus={!auth.enabled}
                    maxLength={40}
                    className="flex-1"
                  />
                  <button
                    type="submit"
                    className={buttonClasses(auth.enabled ? "secondary" : "primary")}
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
            </div>
          )}
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
