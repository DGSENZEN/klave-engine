"use client";

import { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, LockKey } from "@phosphor-icons/react";
import { completeProfile } from "@/lib/identity";
import { apiMessage, resetInfo, resetPassword } from "@/lib/session";
import { AuthFrame, useQueryParam } from "@/components/AuthFrame";
import { buttonClasses, Callout, Card, Input, Skeleton } from "@/components/ui";

export default function RestablecerPage() {
  const router = useRouter();
  const token = useQueryParam("token");
  const [info, setInfo] = useState<{ valid: boolean; email?: string; name?: string } | null>(
    null,
  );
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
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
    if (password !== confirm) {
      setError("Las contraseñas no coinciden.");
      return;
    }
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
      sub="El enlace se usa una sola vez; al terminar cerramos tus otras sesiones."
    >
      {info === null ? (
        <Card className="p-6">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="mt-3 h-9" />
          <Skeleton className="mt-2 h-9" />
        </Card>
      ) : !info.valid ? (
        <Card className="p-6">
          <Callout tone="danger">
            Este enlace ya no es válido: caducó, ya se usó o se generó uno más nuevo.
          </Callout>
          <Link href="/recuperar" className={buttonClasses("secondary", "md", "mt-4 w-full")}>
            Pedir otro enlace
          </Link>
        </Card>
      ) : (
        <Card className="p-6">
          <div className="mb-4 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-2 text-foreground">
              <LockKey size={20} weight="duotone" />
            </div>
            <div className="min-w-0">
              <div className="text-sm font-medium">{info.name}</div>
              <div className="truncate text-xs text-muted">{info.email}</div>
            </div>
          </div>
          <form onSubmit={submit} className="space-y-3">
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Nueva contraseña (mínimo 8 caracteres)"
              minLength={8}
              autoFocus
              required
              className="w-full"
            />
            <Input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Repite la contraseña"
              minLength={8}
              required
              className="w-full"
            />
            {error && <p className="text-sm text-danger">{error}</p>}
            <button type="submit" className={buttonClasses("primary", "md", "w-full")} disabled={busy}>
              Guardar y entrar <ArrowRight size={15} weight="bold" />
            </button>
          </form>
        </Card>
      )}
    </AuthFrame>
  );
}
