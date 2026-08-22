"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, GoogleLogo, HandWaving } from "@phosphor-icons/react";
import { completeProfile } from "@/lib/identity";
import {
  acceptInvitation,
  apiMessage,
  googleLoginUrl,
  invitationInfo,
  type InvitationInfo,
} from "@/lib/session";
import { AuthFrame, useQueryParam } from "@/components/AuthFrame";
import { Badge, buttonClasses, Callout, Card, Input, Skeleton } from "@/components/ui";

type State =
  | { kind: "loading" }
  | { kind: "missing" }
  | { kind: "ready"; info: InvitationInfo; token: string };

export default function InvitacionPage() {
  const token = useQueryParam("token");
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    if (token === undefined) return;
    if (!token) {
      const handle = window.setTimeout(() => setState({ kind: "missing" }), 0);
      return () => window.clearTimeout(handle);
    }
    let active = true;
    invitationInfo(token)
      .then((info) => active && setState({ kind: "ready", info, token }))
      .catch(() => active && setState({ kind: "missing" }));
    return () => {
      active = false;
    };
  }, [token]);

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
        <Card className="p-6">
          <Skeleton className="h-4 w-56" />
          <Skeleton className="mt-3 h-9" />
          <Skeleton className="mt-2 h-9" />
        </Card>
      ) : state.kind === "missing" ? (
        <Card className="p-6">
          <Callout tone="danger">
            No encontramos esta invitación. Pide a tu administrador que la genere de nuevo.
          </Callout>
        </Card>
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
    <Card className="p-6">
      <Callout tone={state === "accepted" ? "info" : "warning"}>
        {state === "accepted"
          ? "Esta invitación ya se usó. Entra con tu correo y contraseña."
          : "Esta invitación ya no es válida; pide una nueva a tu administrador."}
      </Callout>
      {state === "accepted" && (
        <Link href="/bienvenida" className={buttonClasses("primary", "md", "mt-4 w-full")}>
          Entrar
        </Link>
      )}
    </Card>
  );
}

function AcceptCard({ info, token }: { info: InvitationInfo; token: string }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirm) {
      setError("Las contraseñas no coinciden.");
      return;
    }
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
    <Card className="p-6">
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

      {info.google_enabled && (
        <>
          <a href={googleLoginUrl(token)} className={buttonClasses("primary", "md", "w-full")}>
            <GoogleLogo size={16} weight="bold" /> Continuar con Google
          </a>
          <p className="mt-2 text-center text-xs text-muted">
            Debe ser la cuenta de Google de {info.email}.
          </p>
          <div className="my-5 flex items-center gap-3 text-xs text-faint">
            <span className="h-px flex-1 bg-border" />
            o con contraseña
            <span className="h-px flex-1 bg-border" />
          </div>
        </>
      )}

      <form onSubmit={submit} className="space-y-3">
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Nombre y apellido"
          maxLength={80}
          autoFocus
          required
          className="w-full"
        />
        <Input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Contraseña (mínimo 8 caracteres)"
          autoComplete="new-password"
          minLength={8}
          required
          className="w-full"
        />
        <Input
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="Repite la contraseña"
          autoComplete="new-password"
          minLength={8}
          required
          className="w-full"
        />
        {error && <p className="text-sm text-danger">{error}</p>}
        <button
          type="submit"
          className={buttonClasses(info.google_enabled ? "secondary" : "primary", "md", "w-full")}
          disabled={busy}
        >
          Crear cuenta y entrar <ArrowRight size={15} weight="bold" />
        </button>
      </form>
    </Card>
  );
}
