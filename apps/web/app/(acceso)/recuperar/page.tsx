"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { ArrowLeft, EnvelopeSimple } from "@phosphor-icons/react";
import { apiMessage, fetchAuthStatus, requestRecovery, type AuthStatus } from "@/lib/session";
import { AuthFrame } from "@/components/AuthFrame";
import {
  AUTH_INPUT,
  Divider,
  Field,
  recallAuthEmail,
  rememberAuthEmail,
  SubmitButton,
} from "@/components/AuthFields";
import { buttonClasses, Callout, Input, Skeleton } from "@/components/ui";

/** Seconds before the same address may ask again; mail can take a minute to land. */
const RESEND_AFTER = 30;

export default function RecuperarPage() {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [wait, setWait] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const handle = window.setTimeout(() => setEmail((current) => current || recallAuthEmail()), 0);
    fetchAuthStatus().then((status) => {
      if (active) setAuth(status);
    });
    return () => {
      active = false;
      window.clearTimeout(handle);
    };
  }, []);

  useEffect(() => {
    if (wait <= 0) return;
    const handle = window.setTimeout(() => setWait((s) => s - 1), 1000);
    return () => window.clearTimeout(handle);
  }, [wait]);

  async function send(address: string) {
    setBusy(true);
    setError(null);
    try {
      await requestRecovery(address);
      rememberAuthEmail(address);
      setSentTo(address);
      setWait(RESEND_AFTER);
    } catch (e) {
      setError(apiMessage(e, "No se pudo enviar el enlace."));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    send(email.trim());
  }

  const back = (
    <Link href="/bienvenida" className="inline-flex items-center gap-1.5 hover:text-foreground">
      <ArrowLeft size={14} weight="bold" /> Volver a entrar
    </Link>
  );

  const failure = error && (
    <div role="alert">
      <Callout tone="danger">{error}</Callout>
    </div>
  );

  if (sentTo) {
    return (
      <AuthFrame title="Revisa tu correo" footer={back}>
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-full bg-success-soft text-success">
          <EnvelopeSimple size={22} weight="duotone" />
        </div>
        <p className="text-sm text-muted">
          Si <span className="font-medium text-foreground">{sentTo}</span> tiene cuenta, le llega
          un enlace para elegir una contraseña nueva. Vale una hora.
        </p>
        <div className="mt-6 space-y-2">
          {failure}
          <button
            type="button"
            onClick={() => send(sentTo)}
            disabled={wait > 0 || busy}
            className={buttonClasses("secondary", "lg", "w-full tabular")}
          >
            {wait > 0 ? `Reenviar en ${wait} s` : "Reenviar"}
          </button>
          <button
            type="button"
            onClick={() => {
              setSentTo(null);
              setError(null);
            }}
            className={buttonClasses("ghost", "lg", "w-full")}
          >
            Usar otro correo
          </button>
        </div>
      </AuthFrame>
    );
  }

  return (
    <AuthFrame title="¿No puedes entrar?" footer={back}>
      {auth === null ? (
        <div className="space-y-4">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-9" />
          <Skeleton className="h-9" />
        </div>
      ) : auth.mail_enabled ? (
        <form onSubmit={submit} className="space-y-4">
          <Field label="Tu correo" htmlFor="correo" hint="Te enviamos un enlace para elegir una contraseña nueva.">
            <Input
              id="correo"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="correo@taller.mx"
              autoComplete="email"
              autoFocus
              required
              className={AUTH_INPUT}
            />
          </Field>
          {failure}
          <SubmitButton busy={busy} label="Enviar enlace" busyLabel="Enviando…" arrow={false} />
        </form>
      ) : (
        <p className="text-sm text-muted">
          Pide a un administrador un enlace para entrar: lo genera en{" "}
          <span className="font-medium text-foreground">Equipo</span> y vale 24 horas.
        </p>
      )}

      {auth && (
        <>
          <Divider>o</Divider>
          <ul className="space-y-3 text-sm">
            <li className="text-muted">
              <span className="font-medium text-foreground">¿Ya no usas ese correo?</span> Un
              administrador puede generarte un enlace en Equipo y pasártelo por otro medio.
            </li>
          </ul>
        </>
      )}
    </AuthFrame>
  );
}
