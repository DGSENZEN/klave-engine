"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { LockKey } from "@phosphor-icons/react";
import { completeProfile } from "@/lib/identity";
import { apiMessage, resetInfo, resetPassword } from "@/lib/session";
import { AuthFrame, useQueryParam } from "@/components/AuthFrame";
import { PasswordField, SubmitButton } from "@/components/AuthFields";
import { buttonClasses, Callout, Skeleton } from "@/components/ui";

export default function RestablecerPage() {
  const router = useRouter();
  const token = useQueryParam("token");
  const [info, setInfo] = useState<{ valid: boolean; email?: string; name?: string } | null>(
    null,
  );
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token === undefined) return;
    if (!token) {
      const handle = window.setTimeout(() => setInfo({ valid: false }), 0);
      return () => window.clearTimeout(handle);
    }
    let active = true;
    resetInfo(token)
      .then((result) => active && setInfo(result))
      .catch(() => active && setInfo({ valid: false }));
    return () => {
      active = false;
    };
  }, [token]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await resetPassword(token!, password);
      if (result.status === "active") {
        completeProfile(info?.name || "");
        router.replace("/");
        return;
      }
      window.location.href = "/bienvenida?pending=1";
    } catch (e) {
      setError(apiMessage(e, "No se pudo cambiar la contraseña."));
      setBusy(false);
    }
  }

  return (
    <AuthFrame
      title="Nueva contraseña"
      sub="Al guardarla cerramos tus otras sesiones."
    >
      {info === null ? (
        <div className="space-y-4">
          <Skeleton className="h-12" />
          <Skeleton className="h-9" />
          <Skeleton className="h-9" />
        </div>
      ) : !info.valid ? (
        <>
          <Callout tone="danger">
            Este enlace ya no es válido: caducó, ya se usó o se generó uno más nuevo.
          </Callout>
          <Link href="/recuperar" className={buttonClasses("primary", "lg", "mt-6 w-full")}>
            Pedir otro enlace
          </Link>
        </>
      ) : (
        <>
          <div className="mb-6 flex items-center gap-3 rounded-lg border border-border p-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-surface-2 text-foreground">
              <LockKey size={18} weight="duotone" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-medium">{info.name}</div>
              <div className="truncate text-xs text-muted">{info.email}</div>
            </div>
          </div>
          <form onSubmit={submit} className="space-y-4">
            <PasswordField
              id="nueva"
              label="Nueva contraseña"
              value={password}
              onChange={setPassword}
              autoComplete="new-password"
              autoFocus
              rule
            />
            {error && (
              <div role="alert">
                <Callout tone="danger">{error}</Callout>
              </div>
            )}
            <SubmitButton busy={busy} label="Guardar y entrar" busyLabel="Guardando…" />
          </form>
        </>
      )}
    </AuthFrame>
  );
}
