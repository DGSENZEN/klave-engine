"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  GoogleLogo,
  HourglassMedium,
  Monitor,
  ShieldCheck,
  SignOut,
  UserCircle,
  UsersThree,
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
import { AuthFrame } from "@/components/AuthFrame";
import { HowItWorks } from "@/components/HowItWorks";
import {
  Avatar,
  Badge,
  buttonClasses,
  Callout,
  Card,
  Checkbox,
  Input,
  Skeleton,
} from "@/components/ui";

type UrlNotice =
  | "pending"
  | "google"
  | "db"
  | "disabled"
  | "invite"
  | "invite_email"
  | null;

const NOTICES: Record<Exclude<UrlNotice, null>, { tone: "info" | "danger"; text: string }> = {
  pending: {
    tone: "info",
    text: "Tu cuenta fue creada y espera la aprobación de un administrador del taller.",
  },
  google: { tone: "danger", text: "No se pudo iniciar sesión con Google. Inténtalo de nuevo." },
  db: {
    tone: "danger",
    text: "La base de datos de usuarios no está disponible. Arráncala con make users-db-up y recarga.",
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
        const error = params.get("error");
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

  return (
    <AuthFrame
      title={workspaceName && auth?.mode === "protected" ? workspaceName : "Bienvenido a Klave"}
      sub="Ingeniería de costos a partir de planos estructurales."
      width="lg"
    >
      {notice && (
        <div className="mb-4">
          <Callout tone={NOTICES[notice].tone}>{NOTICES[notice].text}</Callout>
        </div>
      )}
      {notice !== "db" && auth?.mode === "unavailable" && (
        <div className="mb-4">
          <Callout tone="danger">{NOTICES.db.text}</Callout>
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
        <AuthCard googleEnabled={auth.google_enabled} mailEnabled={auth.mail_enabled} />
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
    </AuthFrame>
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
      <Link
        href="/cuenta"
        className="mt-4 flex items-center gap-2 border-t border-border pt-3 text-xs font-medium text-muted transition hover:text-foreground"
      >
        <UserCircle size={14} weight="bold" /> Tu cuenta: contraseña, correo y sesiones
      </Link>
    </Card>
  );
}

/* ------------------------------------------------------- protected mode --- */

function AuthCard({
  googleEnabled,
  mailEnabled,
}: {
  googleEnabled: boolean;
  mailEnabled: boolean;
}) {
  const router = useRouter();
  const [tab, setTab] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [registered, setRegistered] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (tab === "login") {
        const user = await login(email.trim(), password, remember);
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
          {mailEnabled && " Te enviamos un correo para confirmar tu dirección."}
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
          autoComplete="email"
          required
          className="w-full"
        />
        <Input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={tab === "register" ? "Contraseña (mínimo 8 caracteres)" : "Contraseña"}
          autoComplete={tab === "register" ? "new-password" : "current-password"}
          minLength={tab === "register" ? 8 : undefined}
          required
          className="w-full"
        />
        {tab === "login" && (
          <div className="flex items-center justify-between gap-3 text-sm">
            <label className="flex cursor-pointer items-center gap-2 text-muted">
              <Checkbox
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
              />
              Recordarme 30 días
            </label>
            <Link href="/recuperar" className="text-muted hover:text-foreground hover:underline">
              ¿Olvidaste tu contraseña?
            </Link>
          </div>
        )}
        {error && <p className="text-sm text-danger">{error}</p>}
        <button type="submit" className={buttonClasses("primary", "md", "w-full")} disabled={busy}>
          {tab === "login" ? "Entrar" : "Crear cuenta"} <ArrowRight size={15} weight="bold" />
        </button>
      </form>
      {tab === "register" && (
        <p className="mt-3 text-xs text-muted">
          Las cuentas nuevas requieren la aprobación de un administrador. Si te invitaron, usa
          el enlace de la invitación: entras de inmediato.
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
      setError(
        apiMessage(e, "No se pudo crear la cuenta. ¿Está corriendo la base de datos?"),
      );
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
              Crea la cuenta de administrador para trabajar en equipo con invitaciones y
              permisos por proyecto.
            </p>
          </div>
        </button>
        {showAccounts && (
          <form onSubmit={createAdmin} className="mt-4 space-y-3 border-t border-border pt-4">
            <div className="flex items-start gap-2 text-xs text-muted">
              <ShieldCheck size={14} className="mt-0.5 shrink-0 text-accent" />
              La primera cuenta es administrador y queda activa. Después invitas a tu equipo
              desde Equipo, o apruebas a quien se registre.
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
