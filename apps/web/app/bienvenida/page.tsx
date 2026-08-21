"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Buildings,
  GoogleLogo,
  HourglassMedium,
  Monitor,
  ShieldCheck,
  SignOut,
  UsersThree,
} from "@phosphor-icons/react";
import { ApiError } from "@/lib/api";
import { peekBrowserActor } from "@/lib/collab";
import { completeProfile } from "@/lib/identity";
import {
  fetchAuthStatus,
  googleLoginUrl,
  login,
  logout,
  register,
  type AuthStatus,
  type AuthUser,
} from "@/lib/session";
import { HowItWorks } from "@/components/HowItWorks";
import { Avatar, Badge, buttonClasses, Callout, Card, Input, Skeleton } from "@/components/ui";
import { ThemeToggle } from "@/components/ThemeToggle";

type UrlNotice = "pending" | "google" | "db" | "disabled" | null;

export default function BienvenidaPage() {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [notice, setNotice] = useState<UrlNotice>(null);

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams(window.location.search);
    const handle = window.setTimeout(() => {
      if (!active) return;
      if (params.get("pending")) setNotice("pending");
      else if (params.get("error") === "google") setNotice("google");
      else if (params.get("error") === "db") setNotice("db");
      else if (params.get("error") === "disabled") setNotice("disabled");
    }, 0);
    fetchAuthStatus().then((status) => {
      if (active) setAuth(status);
    });
    return () => {
      active = false;
      window.clearTimeout(handle);
    };
  }, []);

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

        {notice === "pending" && (
          <div className="mb-4">
            <Callout tone="info">
              Tu cuenta fue creada y espera la aprobación de un administrador del taller.
            </Callout>
          </div>
        )}
        {notice === "google" && (
          <div className="mb-4">
            <Callout tone="danger">
              No se pudo iniciar sesión con Google. Inténtalo de nuevo.
            </Callout>
          </div>
        )}
        {notice === "disabled" && (
          <div className="mb-4">
            <Callout tone="danger">Tu cuenta está deshabilitada.</Callout>
          </div>
        )}
        {(notice === "db" || auth?.mode === "unavailable") && (
          <div className="mb-4">
            <Callout tone="danger">
              La base de datos de usuarios no está disponible. Arráncala con{" "}
              <code className="font-mono text-xs">make users-db-up</code> y recarga.
            </Callout>
          </div>
        )}

        {auth === null ? (
          <Card className="mb-6 p-6">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="mt-3 h-9" />
          </Card>
        ) : auth.user ? (
          <SessionCard user={auth.user} />
        ) : auth.mode === "protected" ? (
          <AuthCard googleEnabled={auth.google_enabled} />
        ) : auth.mode === "open" ? (
          <OpenModeCards googleEnabled={auth.google_enabled} />
        ) : null}

        <HowItWorks />

        {auth?.mode === "open" && (
          <p className="mt-6 flex items-center gap-2 text-xs text-faint">
            <Monitor size={14} />
            Modo local: tus planos y presupuestos se procesan y guardan en tu equipo.
          </p>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------- active session --- */

function SessionCard({ user }: { user: AuthUser }) {
  const router = useRouter();
  const [name, setName] = useState("");

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setName(peekBrowserActor() || user.name);
    }, 0);
    return () => window.clearTimeout(handle);
  }, [user.name]);

  async function onLogout() {
    await logout();
    window.location.reload();
  }

  if (user.status === "pending") {
    return (
      <Card className="mb-6 p-6 text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-warning-soft text-warning">
          <HourglassMedium size={22} weight="duotone" />
        </div>
        <p className="font-medium">Tu cuenta espera aprobación</p>
        <p className="mx-auto mt-1 max-w-sm text-sm text-muted">
          Un administrador del taller debe aprobar tu cuenta ({user.email}) antes de que
          puedas entrar a los proyectos.
        </p>
        <button type="button" onClick={onLogout} className={buttonClasses("ghost", "sm", "mt-4")}>
          <SignOut size={14} weight="bold" /> Cerrar sesión
        </button>
      </Card>
    );
  }

  function continueToWorkspace(event: FormEvent) {
    event.preventDefault();
    completeProfile(name.trim() || user.name);
    router.replace("/");
  }

  return (
    <Card className="mb-6 p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar name={user.name} src={user.picture} self />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-medium">{user.name}</span>
              {user.role === "admin" && <Badge tone="accent">Admin</Badge>}
            </div>
            <div className="truncate text-xs text-muted">{user.email}</div>
          </div>
        </div>
        <button type="button" onClick={onLogout} className={buttonClasses("ghost", "sm")}>
          <SignOut size={14} weight="bold" /> Cerrar sesión
        </button>
      </div>
      <form onSubmit={continueToWorkspace}>
        <label htmlFor="nombre" className="mb-1.5 block text-sm font-medium">
          Nombre visible en los proyectos
        </label>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Input
            id="nombre"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={40}
            className="flex-1"
          />
          <button type="submit" className={buttonClasses("primary")}>
            Continuar <ArrowRight size={15} weight="bold" />
          </button>
        </div>
      </form>
    </Card>
  );
}

/* ------------------------------------------------------- protected mode --- */

function AuthCard({ googleEnabled }: { googleEnabled: boolean }) {
  const router = useRouter();
  const [tab, setTab] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [registered, setRegistered] = useState(false);

  function apiMessage(e: unknown, fallback: string): string {
    if (e instanceof ApiError && e.detail && typeof e.detail === "object") {
      const message = (e.detail as { message?: string }).message;
      if (message) return message;
    }
    return fallback;
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (tab === "login") {
        const user = await login(email.trim(), password);
        if (user.status === "active") {
          completeProfile(user.name);
          router.replace("/");
          return;
        }
        window.location.href = "/bienvenida?pending=1";
      } else {
        const user = await register(email.trim(), name.trim(), password);
        if (user.status === "active") {
          completeProfile(user.name);
          router.replace("/");
          return;
        }
        setRegistered(true);
      }
    } catch (e) {
      setError(apiMessage(e, "No se pudo completar la operación."));
    } finally {
      setBusy(false);
    }
  }

  if (registered) {
    return (
      <Card className="mb-6 p-6 text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-warning-soft text-warning">
          <HourglassMedium size={22} weight="duotone" />
        </div>
        <p className="font-medium">Cuenta creada</p>
        <p className="mx-auto mt-1 max-w-sm text-sm text-muted">
          Un administrador del taller debe aprobarla; después podrás entrar con tu correo y
          contraseña.
        </p>
      </Card>
    );
  }

  return (
    <Card className="mb-6 p-6">
      <div className="mb-5 flex rounded-lg border border-border bg-surface-2/60 p-0.5">
        {(["login", "register"] as const).map((key) => (
          <button
            key={key}
            type="button"
            onClick={() => {
              setTab(key);
              setError(null);
            }}
            className={`flex-1 rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              tab === key ? "bg-surface text-foreground shadow-xs" : "text-muted hover:text-foreground"
            }`}
          >
            {key === "login" ? "Entrar" : "Crear cuenta"}
          </button>
        ))}
      </div>

      {googleEnabled && (
        <>
          <a href={googleLoginUrl()} className={buttonClasses("primary", "md", "w-full")}>
            <GoogleLogo size={16} weight="bold" /> Continuar con Google
          </a>
          <div className="my-5 flex items-center gap-3 text-xs text-faint">
            <span className="h-px flex-1 bg-border" />
            o con tu correo
            <span className="h-px flex-1 bg-border" />
          </div>
        </>
      )}

      <form onSubmit={submit} className="space-y-3">
        {tab === "register" && (
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Nombre y apellido"
            maxLength={80}
            required
            className="w-full"
          />
        )}
        <Input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="correo@taller.mx"
          required
          className="w-full"
        />
        <Input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={tab === "register" ? "Contraseña (mínimo 8 caracteres)" : "Contraseña"}
          minLength={tab === "register" ? 8 : undefined}
          required
          className="w-full"
        />
        {error && <p className="text-sm text-danger">{error}</p>}
        <button type="submit" className={buttonClasses("primary", "md", "w-full")} disabled={busy}>
          {tab === "login" ? "Entrar" : "Crear cuenta"} <ArrowRight size={15} weight="bold" />
        </button>
      </form>
      {tab === "register" && (
        <p className="mt-3 text-xs text-muted">
          Las cuentas nuevas requieren la aprobación de un administrador del taller.
        </p>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------ open mode --- */

function OpenModeCards({ googleEnabled }: { googleEnabled: boolean }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [touched, setTouched] = useState(false);
  const [showAccounts, setShowAccounts] = useState(false);
  const [adminName, setAdminName] = useState("");
  const [adminEmail, setAdminEmail] = useState("");
  const [adminPassword, setAdminPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setName((current) => current || peekBrowserActor());
    }, 0);
    return () => window.clearTimeout(handle);
  }, []);

  const valid = name.trim().length >= 2;

  function startLocal(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (!valid) return;
    completeProfile(name);
    router.replace("/");
  }

  async function createAdmin(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await register(adminEmail.trim(), adminName.trim(), adminPassword);
      completeProfile(user.name);
      router.replace("/");
    } catch (e) {
      const message =
        e instanceof ApiError && e.detail && typeof e.detail === "object"
          ? (e.detail as { message?: string }).message
          : null;
      setError(message || "No se pudo crear la cuenta. ¿Está corriendo la base de datos?");
      setBusy(false);
    }
  }

  return (
    <>
      <Card className="mb-4 p-6">
        <form onSubmit={startLocal}>
          <label htmlFor="nombre" className="mb-1.5 block text-sm font-medium">
            ¿Cómo te llamas?
          </label>
          <p className="mb-3 text-sm text-muted">
            Tu nombre identifica tus cambios y tu presencia cuando colaboras en un proyecto.
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
            <button type="submit" className={buttonClasses("primary")} disabled={touched && !valid}>
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

      <Card className="mb-6 p-6">
        <button
          type="button"
          onClick={() => setShowAccounts((current) => !current)}
          className="flex w-full items-center gap-3 text-left"
        >
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-foreground">
            <UsersThree size={18} weight="duotone" />
          </div>
          <div className="flex-1">
            <div className="text-sm font-medium">Activar cuentas del taller</div>
            <p className="text-sm text-muted">
              Crea la cuenta de administrador para trabajar en equipo con permisos por
              proyecto.
            </p>
          </div>
        </button>
        {showAccounts && (
          <form onSubmit={createAdmin} className="mt-4 space-y-3 border-t border-border pt-4">
            <div className="flex items-start gap-2 text-xs text-muted">
              <ShieldCheck size={14} className="mt-0.5 shrink-0 text-accent" />
              La primera cuenta es administrador y queda activa. Cada registro posterior
              espera tu aprobación en Equipo.
              {googleEnabled && " También podrás entrar con Google."}
            </div>
            <Input
              value={adminName}
              onChange={(e) => setAdminName(e.target.value)}
              placeholder="Nombre y apellido"
              maxLength={80}
              required
              className="w-full"
            />
            <Input
              type="email"
              value={adminEmail}
              onChange={(e) => setAdminEmail(e.target.value)}
              placeholder="correo@taller.mx"
              required
              className="w-full"
            />
            <Input
              type="password"
              value={adminPassword}
              onChange={(e) => setAdminPassword(e.target.value)}
              placeholder="Contraseña (mínimo 8 caracteres)"
              minLength={8}
              required
              className="w-full"
            />
            {error && <p className="text-sm text-danger">{error}</p>}
            <button type="submit" className={buttonClasses("primary", "md", "w-full")} disabled={busy}>
              Crear cuenta de administrador
            </button>
          </form>
        )}
      </Card>
    </>
  );
}
