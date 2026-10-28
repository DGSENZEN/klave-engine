"use client";

import { consumeSessionReturn } from "@/lib/sessionReturn";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  CaretDown,
  GoogleLogo,
  HourglassMedium,
  SignOut,
  UserCircle,
} from "@phosphor-icons/react";
import { peekBrowserActor } from "@/lib/collab";
import { completeProfile } from "@/lib/identity";
import {
  apiMessage,
  fetchAuthStatus,
  googleLoginUrl,
  login,
  logout,
  register,
  type AuthStatus,
  type AuthUser,
} from "@/lib/session";
import { AuthFrame, AuthSwitch } from "@/components/AuthFrame";
import {
  Divider,
  Field,
  PasswordField,
  recallAuthEmail,
  rememberAuthEmail,
} from "@/components/AuthFields";
import { Avatar, Badge, buttonClasses, Callout, Checkbox, Input, Skeleton } from "@/components/ui";

type UrlNotice =
  | "session_expired"
  | "pending"
  | "google"
  | "google_unverified"
  | "google_link_required"
  | "db"
  | "disabled"
  | "invite"
  | "invite_email"
  | null;

const NOTICES: Record<Exclude<UrlNotice, null>, { tone: "info" | "danger"; text: string }> = {
  session_expired: { tone: "info", text: "Tu sesión terminó. Inicia sesión para continuar donde estabas." },
  pending: {
    tone: "info",
    text: "Tu cuenta fue creada y espera la aprobación de un administrador del taller.",
  },
  google: { tone: "danger", text: "No se pudo iniciar sesión con Google. Inténtalo de nuevo." },
  google_unverified: {
    tone: "danger",
    text: "Google no ha verificado el correo de esa cuenta; verifica tu correo en Google o entra con contraseña.",
  },
  google_link_required: {
    tone: "info",
    text: "Ya existe una cuenta con ese correo. Entra con tu contraseña y vincula Google desde Tu cuenta; así nadie puede tomar tu cuenta solo con un correo parecido.",
  },
  db: {
    tone: "danger",
    text: "La base de datos de usuarios no está disponible; inténtalo de nuevo o contacta al administrador del taller.",
  },
  disabled: { tone: "danger", text: "Tu cuenta está deshabilitada." },
  invite: { tone: "danger", text: "La invitación ya no es válida; pide una nueva a tu administrador." },
  invite_email: {
    tone: "danger",
    text: "La cuenta de Google no coincide con el correo invitado. Usa esa cuenta o crea la contraseña.",
  },
};

export default function BienvenidaPage() {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [notice, setNotice] = useState<UrlNotice>(null);

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams(window.location.search);
    const handle = window.setTimeout(() => {
      if (!active) return;
      if (params.get("pending")) setNotice("pending");
      else {
        const error = params.get("error") ?? params.get("reason");
        if (error && error in NOTICES) setNotice(error as UrlNotice);
      }
    }, 0);
    fetchAuthStatus().then((status) => {
      if (active) setAuth(status);
    });
    return () => {
      active = false;
      window.clearTimeout(handle);
    };
  }, []);

  const workspaceName = auth?.workspace?.name;
  const signingIn = auth?.mode === "protected" && !auth.user;
  const canRegister = signingIn && auth.registration !== "invite_only";

  return (
    <AuthFrame
      title={workspaceName && auth?.mode === "protected" ? workspaceName : "Bienvenido a Klave"}
      footer={
        signingIn && !canRegister ? "¿Sin cuenta? Pide una invitación a tu administrador." : undefined
      }
    >
      {canRegister && <AuthSwitch current="entrar" />}
      {notice && (
        <div className="mb-5">
          <Callout tone={NOTICES[notice].tone}>{NOTICES[notice].text}</Callout>
        </div>
      )}
      {notice !== "db" && auth?.mode === "unavailable" && (
        <div className="mb-5">
          <Callout tone="danger">
            {auth.failure === "users_db" ? NOTICES.db.text
              : auth.failure === "network" ? "No pudimos conectar con Klave. Revisa tu conexión e inténtalo de nuevo."
              : "Klave no está disponible por el momento. Inténtalo de nuevo o contacta a tu administrador."}
            <button type="button" className="ml-2 underline" onClick={() => window.location.reload()}>Reintentar</button>
          </Callout>
        </div>
      )}

      {auth === null ? (
        <div className="space-y-4">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-9" />
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-9" />
        </div>
      ) : auth.user ? (
        <SessionPanel user={auth.user} />
      ) : auth.mode === "protected" ? (
        <SignInForm googleEnabled={auth.google_enabled} />
      ) : auth.mode === "open" ? (
        <OpenModePanel googleEnabled={auth.google_enabled} />
      ) : null}
    </AuthFrame>
  );
}

/* ------------------------------------------------------- active session --- */

function SessionPanel({ user }: { user: AuthUser }) {
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
      <div>
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-warning-soft text-warning">
          <HourglassMedium size={22} weight="duotone" />
        </div>
        <p className="font-medium">Tu cuenta espera aprobación</p>
        <p className="mt-1 text-sm text-muted">
          Un administrador del taller debe aprobar tu cuenta ({user.email}) antes de que
          puedas entrar a los proyectos.
        </p>
        <button type="button" onClick={onLogout} className={buttonClasses("secondary", "md", "mt-6 w-full")}>
          <SignOut size={14} weight="bold" /> Cerrar sesión
        </button>
      </div>
    );
  }

  function continueToWorkspace(event: FormEvent) {
    event.preventDefault();
    completeProfile(name.trim() || user.name);
    router.replace(consumeSessionReturn());
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between gap-3 rounded-lg border border-border p-3">
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
          <SignOut size={14} weight="bold" /> Salir
        </button>
      </div>
      <form onSubmit={continueToWorkspace} className="space-y-4">
        <Field label="Nombre visible en los proyectos" htmlFor="nombre">
          <Input
            id="nombre"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={40}
            className="w-full"
          />
        </Field>
        <button type="submit" className={buttonClasses("primary", "md", "w-full")}>
          Continuar <ArrowRight size={15} weight="bold" />
        </button>
      </form>
      <Link
        href="/cuenta"
        className="mt-6 flex items-center gap-2 text-xs font-medium text-muted transition hover:text-foreground"
      >
        <UserCircle size={14} weight="bold" /> Tu cuenta: contraseña, correo y sesiones
      </Link>
    </div>
  );
}

/* -------------------------------------------------------------- sign in --- */

function SignInForm({ googleEnabled }: { googleEnabled: boolean }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const handle = window.setTimeout(() => setEmail((current) => current || recallAuthEmail()), 0);
    return () => window.clearTimeout(handle);
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await login(email.trim(), password, remember);
      if (user.status === "active") {
        completeProfile(user.name);
        router.replace(consumeSessionReturn());
        return;
      }
      window.location.href = "/bienvenida?pending=1";
    } catch (e) {
      setError(apiMessage(e, "No se pudo iniciar sesión."));
      setBusy(false);
    }
  }

  return (
    <>
      {googleEnabled && (
        <>
          <a href={googleLoginUrl()} className={buttonClasses("secondary", "md", "w-full")}>
            <GoogleLogo size={16} weight="bold" /> Continuar con Google
          </a>
          <Divider>o</Divider>
        </>
      )}
      <form onSubmit={submit} className="space-y-4">
        <Field label="Correo electrónico" htmlFor="correo">
          <Input
            id="correo"
            type="email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              rememberAuthEmail(e.target.value);
            }}
            placeholder="correo@taller.mx"
            autoComplete="email"
            autoFocus
            required
            className="w-full"
          />
        </Field>
        <PasswordField
          id="contrasena"
          label="Contraseña"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
          aside={
            <Link href="/recuperar" className="text-xs text-muted hover:text-foreground hover:underline">
              ¿No puedes entrar?
            </Link>
          }
        />
        <Checkbox
          label={<span className="text-muted">Recordarme 30 días</span>}
          checked={remember}
          onChange={(e) => setRemember(e.target.checked)}
        />
        {error && (
          <div role="alert">
            <Callout tone="danger">{error}</Callout>
          </div>
        )}
        <button type="submit" className={buttonClasses("primary", "md", "w-full")} disabled={busy}>
          Entrar <ArrowRight size={15} weight="bold" />
        </button>
      </form>
    </>
  );
}

/* ------------------------------------------------------------ open mode --- */

function OpenModePanel({ googleEnabled }: { googleEnabled: boolean }) {
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
    router.replace(consumeSessionReturn());
  }

  async function createAdmin(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await register(adminEmail.trim(), adminName.trim(), adminPassword);
      completeProfile(user.name);
      router.replace(consumeSessionReturn());
    } catch (e) {
      setError(
        apiMessage(e, "No se pudo crear la cuenta. ¿Está corriendo la base de datos?"),
      );
      setBusy(false);
    }
  }

  return (
    <>
      <form onSubmit={startLocal} className="space-y-4">
        <Field label="Tu nombre" htmlFor="nombre">
          <Input
            id="nombre"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Nombre y apellido"
            autoComplete="name"
            autoFocus
            maxLength={40}
            className="w-full"
          />
        </Field>
        {touched && !valid && (
          <p role="alert" className="text-sm text-danger">
            Escribe un nombre de al menos 2 caracteres.
          </p>
        )}
        <button type="submit" className={buttonClasses("primary", "md", "w-full")} disabled={touched && !valid}>
          Comenzar <ArrowRight size={15} weight="bold" />
        </button>
      </form>

      <div className="mt-8 border-t border-border pt-5">
        <button
          type="button"
          onClick={() => setShowAccounts((current) => !current)}
          aria-expanded={showAccounts}
          className="flex w-full items-center justify-between gap-3 text-left text-sm font-medium text-muted transition-colors hover:text-foreground"
        >
          Activar cuentas para trabajar en equipo
          <CaretDown
            size={14}
            className={`shrink-0 transition-transform ${showAccounts ? "rotate-180" : ""}`}
          />
        </button>
        {showAccounts && (
          <form onSubmit={createAdmin} className="mt-5 space-y-4">
            <p className="text-xs text-muted">
              La primera cuenta es la de administrador
              {googleEnabled ? "; después también podrás entrar con Google." : "."}
            </p>
            <Field label="Nombre y apellido" htmlFor="admin-nombre">
              <Input
                id="admin-nombre"
                value={adminName}
                onChange={(e) => setAdminName(e.target.value)}
                autoComplete="name"
                maxLength={80}
                required
                className="w-full"
              />
            </Field>
            <Field label="Correo electrónico" htmlFor="admin-correo">
              <Input
                id="admin-correo"
                type="email"
                value={adminEmail}
                onChange={(e) => setAdminEmail(e.target.value)}
                placeholder="correo@taller.mx"
                autoComplete="email"
                required
                className="w-full"
              />
            </Field>
            <PasswordField
              id="admin-contrasena"
              label="Contraseña"
              value={adminPassword}
              onChange={setAdminPassword}
              autoComplete="new-password"
              rule
            />
            {error && (
              <div role="alert">
                <Callout tone="danger">{error}</Callout>
              </div>
            )}
            <button type="submit" className={buttonClasses("primary", "md", "w-full")} disabled={busy}>
              Crear cuenta de administrador
            </button>
          </form>
        )}
      </div>
    </>
  );
}
