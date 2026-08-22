"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { ArrowLeft, EnvelopeSimple, ShieldCheck } from "@phosphor-icons/react";
import { apiMessage, fetchAuthStatus, requestRecovery } from "@/lib/session";
import { AuthFrame } from "@/components/AuthFrame";
import { buttonClasses, Callout, Card, Input, Skeleton } from "@/components/ui";

export default function RecuperarPage() {
  const [mailEnabled, setMailEnabled] = useState<boolean | null>(null);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    fetchAuthStatus().then((status) => {
      if (active) setMailEnabled(status.mail_enabled);
    });
    return () => {
      active = false;
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await requestRecovery(email.trim());
      setSent(true);
    } catch (e) {
      setError(apiMessage(e, "No se pudo enviar la solicitud."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthFrame
      title="Recuperar acceso"
      sub="Te enviamos un enlace para elegir una contraseña nueva."
      footer={
        <Link href="/bienvenida" className="inline-flex items-center gap-1.5 hover:text-foreground">
          <ArrowLeft size={14} weight="bold" /> Volver a entrar
        </Link>
      }
    >
      {mailEnabled === null ? (
        <Card className="p-6">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="mt-3 h-9" />
        </Card>
      ) : !mailEnabled ? (
        <Card className="p-6">
          <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-surface-2 text-foreground">
            <ShieldCheck size={20} weight="duotone" />
          </div>
          <p className="font-medium">Este taller entrega los enlaces a mano</p>
          <p className="mt-1 text-sm text-muted">
            No hay envío de correos configurado. Pide a un administrador que genere tu
            enlace de recuperación desde <span className="font-medium text-foreground">Equipo</span>;
            vale 24 horas y se usa una sola vez.
          </p>
        </Card>
      ) : sent ? (
        <Card className="p-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-success-soft text-success">
            <EnvelopeSimple size={22} weight="duotone" />
          </div>
          <p className="font-medium">Revisa tu correo</p>
          <p className="mx-auto mt-1 max-w-sm text-sm text-muted">
            Si existe una cuenta para {email.trim()}, le enviamos un enlace que vale una hora.
          </p>
        </Card>
      ) : (
        <Card className="p-6">
          <form onSubmit={submit} className="space-y-3">
            <label htmlFor="correo" className="block text-sm font-medium">
              Correo de tu cuenta
            </label>
            <Input
              id="correo"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="correo@taller.mx"
              autoFocus
              required
              className="w-full"
            />
            {error && <Callout tone="danger">{error}</Callout>}
            <button type="submit" className={buttonClasses("primary", "md", "w-full")} disabled={busy}>
              Enviar enlace
            </button>
          </form>
        </Card>
      )}
    </AuthFrame>
  );
}
