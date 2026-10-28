"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, CircleNotch, HandWaving } from "@phosphor-icons/react";
import { completeProfile } from "@/lib/identity";
import {
  acceptInvitation,
  apiMessage,
  invitationInfo,
  type InvitationInfo,
} from "@/lib/session";
import { AuthFrame, useQueryParam } from "@/components/AuthFrame";
import { AUTH_INPUT, Field, PasswordField } from "@/components/AuthFields";
import { Badge, buttonClasses, Callout, Input, Skeleton } from "@/components/ui";

type State =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "service-error" }
  | { kind: "ready"; info: InvitationInfo; token: string };

export default function InvitacionPage() {
  const token = useQueryParam("token");
  const [state, setState] = useState<State>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (token === undefined) return;
    if (!token) {
      const handle = window.setTimeout(() => setState({ kind: "missing" }), 0);
      return () => window.clearTimeout(handle);
    }
    let active = true;
    invitationInfo(token)
      .then((info) => active && setState({ kind: "ready", info, token }))
      .catch((error) => {
        if (!active) return;
        const status = error && typeof error === "object" && "status" in error ? error.status : 0;
        setState({ kind: status === 404 || status === 410 ? "missing" : "service-error" });
      });
    return () => {
      active = false;
    };
  }, [token, attempt]);

  return (
    <AuthFrame
      title="Invitación"
      sub={
        state.kind === "ready"
          ? `Únete a ${state.info.workspace_name}`
          : "Crea tu cuenta y entra al taller."
      }
      footer={
        <span>
          ¿Ya tienes cuenta?{" "}
          <Link href="/bienvenida" className="font-medium text-foreground hover:underline">
            Entrar
          </Link>
        </span>
      }
    >
      {state.kind === "loading" ? (
        <div>
          <Skeleton className="h-4 w-56" />
          <Skeleton className="mt-3 h-9" />
          <Skeleton className="mt-2 h-9" />
        </div>
      ) : state.kind === "service-error" ? (
        <div>
          <Callout tone="warning">
            No pudimos consultar la invitación. Revisa tu conexión e inténtalo de nuevo.
          </Callout>
          <button type="button" className={buttonClasses("secondary", "lg", "mt-4")}
            onClick={() => { setState({ kind: "loading" }); setAttempt((n) => n + 1); }}>
            Reintentar
          </button>
        </div>
      ) : state.kind === "missing" ? (
        <div>
          <Callout tone="danger">
            No encontramos esta invitación. Pide a tu administrador que la genere de nuevo.
          </Callout>
        </div>
      ) : state.info.state !== "open" ? (
        <ClosedCard state={state.info.state} />
      ) : (
        <AcceptCard info={state.info} token={state.token} />
      )}
    </AuthFrame>
  );
}

function ClosedCard({ state }: { state: InvitationInfo["state"] }) {
  return (
    <div>
      <Callout tone={state === "accepted" ? "info" : "warning"}>
        {state === "accepted"
          ? "Esta invitación ya se usó. Entra con tu correo y contraseña."
          : "Esta invitación ya no es válida; pide una nueva a tu administrador."}
      </Callout>
      {state === "accepted" && (
        <Link href="/bienvenida" className={buttonClasses("primary", "lg", "mt-4 w-full")}>
          Entrar
        </Link>
      )}
    </div>
  );
}

function AcceptCard({ info, token }: { info: InvitationInfo; token: string }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await acceptInvitation(token, name.trim(), password);
      completeProfile(user.name);
      router.replace("/");
    } catch (e) {
      setError(apiMessage(e, "No se pudo aceptar la invitación."));
      setBusy(false);
    }
  }

  const projects = info.project_count;

  return (
    <div>
      <div className="mb-5 flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">
          <HandWaving size={20} weight="duotone" />
        </div>
        <div className="min-w-0 text-sm">
          <p>
            <span className="font-medium">{info.inviter_name || "Un administrador"}</span> te invitó
            como{" "}
            <Badge tone={info.role === "admin" ? "accent" : "default"}>
              {info.role === "admin" ? "Administrador" : "Miembro"}
            </Badge>
          </p>
          <p className="mt-1 text-muted">
            La cuenta se crea para{" "}
            <span className="font-medium text-foreground">{info.email}</span>
            {projects > 0 && ` con acceso a ${projects} proyecto${projects === 1 ? "" : "s"}`}.
          </p>
        </div>
      </div>

      <form onSubmit={submit} className="space-y-4">
        <Field label="Nombre y apellido" htmlFor="nombre">
          <Input
            id="nombre"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoComplete="name"
            maxLength={80}
            autoFocus
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
        {error && (
          <div role="alert">
            <Callout tone="danger">{error}</Callout>
          </div>
        )}
        <button
          type="submit"
          className={buttonClasses("primary", "lg", "w-full")}
          disabled={busy}
          aria-busy={busy}
        >
          {busy ? (
            <>
              <CircleNotch size={15} className="animate-spin" /> Creando cuenta…
            </>
          ) : (
            <>
              Crear cuenta y entrar <ArrowRight size={15} weight="bold" />
            </>
          )}
        </button>
      </form>
    </div>
  );
}
