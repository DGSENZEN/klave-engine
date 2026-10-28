"use client";

import { consumeSessionReturn } from "@/lib/sessionReturn";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowRight, GoogleLogo, HourglassMedium } from "@phosphor-icons/react";
import { completeProfile } from "@/lib/identity";
import { apiMessage, fetchAuthStatus, googleLoginUrl, register, type AuthStatus } from "@/lib/session";
import { AuthFrame, AuthSwitch } from "@/components/AuthFrame";
import {
  AUTH_INPUT,
  Divider,
  Field,
  PasswordField,
  recallAuthEmail,
  rememberAuthEmail,
  SubmitButton,
} from "@/components/AuthFields";
import { buttonClasses, Callout, Checkbox, Input, Skeleton } from "@/components/ui";

export default function RegistroPage() {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [created, setCreated] = useState<{ email: string } | null>(null);

  useEffect(() => {
    let active = true;
    fetchAuthStatus().then((status) => {
      if (active) setAuth(status);
    });
    return () => {
      active = false;
    };
  }, []);

  const signingUp =
    auth?.mode === "protected" && !auth.user && auth.registration !== "invite_only" && !created;

  const backToSignIn = (
    <span>
      ¿Ya tienes cuenta?{" "}
      <Link href="/bienvenida" className="font-medium text-foreground hover:underline">
        Entrar
      </Link>
    </span>
  );

  if (created) {
    return (
      <AuthFrame title="Cuenta creada" footer={backToSignIn}>
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-warning-soft text-warning">
          <HourglassMedium size={22} weight="duotone" />
        </div>
        <p className="text-sm text-muted">
          Cuando un administrador apruebe{" "}
          <span className="font-medium text-foreground">{created.email}</span>, podrás entrar.
          {auth?.mail_enabled && " Revisa tu correo para confirmar la dirección."}
        </p>
      </AuthFrame>
    );
  }

  return (
    <AuthFrame
      title={auth?.mode === "protected" && auth.workspace?.name ? auth.workspace.name : "Crear cuenta"}
      footer={signingUp ? undefined : backToSignIn}
    >
      {signingUp && <AuthSwitch current="registro" />}
      {auth === null ? (
        <div className="space-y-4">
          <Skeleton className="h-9" />
          <Skeleton className="h-9" />
          <Skeleton className="h-9" />
        </div>
      ) : auth.mode === "unavailable" ? (
        <Callout tone="danger">
          Klave no está disponible por el momento. Inténtalo de nuevo o contacta a tu administrador.
        </Callout>
      ) : auth.user ? (
        <Elsewhere text="Ya tienes una sesión abierta en este navegador." action="Continuar" />
      ) : auth.mode === "open" ? (
        <Elsewhere
          text="Esta instalación todavía no usa cuentas: empieza con tu nombre."
          action="Empezar"
        />
      ) : auth.registration === "invite_only" ? (
        <Elsewhere
          text="Este taller es solo por invitación. Pide tu enlace a un administrador."
          action="Volver a entrar"
          back
        />
      ) : (
        <SignUpForm googleEnabled={auth.google_enabled} onPending={setCreated} />
      )}
    </AuthFrame>
  );
}

function Elsewhere({ text, action, back = false }: { text: string; action: string; back?: boolean }) {
  return (
    <>
      <p className="text-sm text-muted">{text}</p>
      <Link href="/bienvenida" className={buttonClasses(back ? "secondary" : "primary", "lg", "mt-6 w-full")}>
        {back && <ArrowLeft size={15} weight="bold" />}
        {action}
        {!back && <ArrowRight size={15} weight="bold" />}
      </Link>
    </>
  );
}

function SignUpForm({
  googleEnabled,
  onPending,
}: {
  googleEnabled: boolean;
  onPending: (created: { email: string }) => void;
}) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [founding, setFounding] = useState(false);
  const [workspaceName, setWorkspaceName] = useState("");
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
      const user = await register(
        email.trim(), name.trim(), password,
        founding ? workspaceName.trim() : undefined,
      );
      if (user.status === "active") {
        completeProfile(user.name);
        router.replace(consumeSessionReturn());
        return;
      }
      onPending({ email: user.email });
    } catch (e) {
      setError(apiMessage(e, "No se pudo crear la cuenta."));
      setBusy(false);
    }
  }

  return (
    <>
      {googleEnabled && (
        <>
          <a href={googleLoginUrl()} className={buttonClasses("secondary", "lg", "w-full")}>
            <GoogleLogo size={16} weight="bold" /> Continuar con Google
          </a>
          <Divider>o</Divider>
        </>
      )}
      <form onSubmit={submit} className="space-y-4">
        <Field label="Nombre y apellido" htmlFor="nombre">
          <Input
            id="nombre"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="name"
            minLength={2}
            maxLength={80}
            autoFocus
            required
            className={AUTH_INPUT}
          />
        </Field>
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
            required
            className={AUTH_INPUT}
          />
        </Field>
        <PasswordField
          id="contrasena"
          label="Contraseña"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          rule
        />

        <Checkbox
          label={<span className="text-muted">Abrir un taller nuevo</span>}
          checked={founding}
          onChange={(e) => setFounding(e.target.checked)}
        />
        {founding && (
          <Field label="Nombre del taller" htmlFor="taller">
            <Input
              id="taller"
              value={workspaceName}
              onChange={(e) => setWorkspaceName(e.target.value)}
              placeholder="p. ej. Constructora GAYA"
              autoComplete="organization"
              minLength={2}
              maxLength={80}
              required
              className={AUTH_INPUT}
            />
          </Field>
        )}

        {error && (
          <div role="alert">
            <Callout tone="danger">{error}</Callout>
          </div>
        )}
        <SubmitButton busy={busy} label="Crear cuenta" busyLabel="Creando cuenta…" />
        <p className="text-center text-xs text-faint">
          {founding
            ? "Entras de inmediato como administrador."
            : "Un administrador del taller aprueba las cuentas nuevas."}
        </p>
      </form>
    </>
  );
}
