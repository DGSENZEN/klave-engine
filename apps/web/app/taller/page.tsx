"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowCounterClockwise, CheckCircle, GearSix } from "@phosphor-icons/react";
import {
  getWorkspaceDefaults,
  renameWorkspace,
  resetWorkspaceDefaults,
  saveWorkspaceDefaults,
  type CostingConfigFull,
  type WorkspaceDefaults,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import { apiMessage, fetchAuthStatus, type AuthStatus } from "@/lib/session";
import { timeAgo } from "@/lib/time";
import { CONFIG_GROUPS, ConfigGroup } from "@/components/CostingConfigForm";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import {
  Badge,
  Button,
  Callout,
  Card,
  Input,
  PageHeader,
  SectionTitle,
  SkeletonCards,
} from "@/components/ui";
import { WorkspaceHeader } from "@/components/WorkspaceHeader";

export default function TallerPage() {
  const router = useRouter();
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [defaults, setDefaults] = useState<WorkspaceDefaults | null>(null);
  const [config, setConfig] = useState<CostingConfigFull | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);

  const load = useCallback(() => {
    getWorkspaceDefaults()
      .then((d) => {
        setDefaults(d);
        setConfig(d.config);
        setDirty(false);
      })
      .catch(() => setError("No se pudieron cargar los valores del taller."));
  }, []);

  useEffect(() => {
    let active = true;
    fetchAuthStatus().then((status) => {
      if (!active) return;
      const allowed = status.mode === "open" || status.user?.role === "admin";
      if (!allowed) {
        router.replace("/");
        return;
      }
      setAuth(status);
      load();
    });
    return () => {
      active = false;
    };
  }, [load, router]);

  function setField(group: keyof CostingConfigFull, key: string, value: number | null) {
    setConfig((c) => (c ? { ...c, [group]: { ...(c[group] as object), [key]: value } } : c));
    setDirty(true);
    setNote(null);
  }

  async function save() {
    if (!config) return;
    setBusy(true);
    setError(null);
    try {
      const saved = await saveWorkspaceDefaults(config, getBrowserActor());
      setDefaults(saved);
      setConfig(saved.config);
      setDirty(false);
      setNote("Guardado. Los proyectos nuevos arrancan con estos valores.");
    } catch (e) {
      setError(apiMessage(e, "No se pudieron guardar los valores."));
    } finally {
      setBusy(false);
    }
  }

  async function reset() {
    setConfirmReset(false);
    setBusy(true);
    setError(null);
    try {
      const saved = await resetWorkspaceDefaults(getBrowserActor());
      setDefaults(saved);
      setConfig(saved.config);
      setDirty(false);
      setNote("Valores restablecidos a los del motor.");
    } catch (e) {
      setError(apiMessage(e, "No se pudieron restablecer los valores."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen">
      <WorkspaceHeader active="taller" />
      <main className="mx-auto max-w-4xl px-5 py-8 pb-28 sm:px-6">
        <PageHeader
          title="Taller"
          sub="Lo que cada proyecto nuevo hereda: nombre del taller, indirectos, supuestos, programa y condiciones financieras. Los proyectos existentes no cambian."
        />
        {error && (
          <div className="mb-4">
            <Callout tone="danger">{error}</Callout>
          </div>
        )}
        {auth === null || config === null || defaults === null ? (
          <SkeletonCards count={3} />
        ) : (
          <div className="space-y-4">
            <NameCard auth={auth} />
            <Card className="flex flex-wrap items-center justify-between gap-3 p-5">
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-2 text-foreground">
                  <GearSix size={18} weight="duotone" />
                </span>
                <div>
                  <div className="flex items-center gap-2 text-sm font-medium">
                    Valores predeterminados de costeo
                    {defaults.customized ? (
                      <Badge tone="accent">Personalizados</Badge>
                    ) : (
                      <Badge>Del motor</Badge>
                    )}
                  </div>
                  <div className="text-xs text-muted">
                    {defaults.customized && defaults.updated_at
                      ? `Actualizados ${timeAgo(defaults.updated_at)}${
                          defaults.updated_by ? ` por ${defaults.updated_by}` : ""
                        }`
                      : "Cada proyecto puede ajustarlos después en Parámetros."}
                  </div>
                </div>
              </div>
              {defaults.customized && (
                <Button size="sm" variant="ghost" onClick={() => setConfirmReset(true)}>
                  <ArrowCounterClockwise size={14} weight="bold" /> Restablecer
                </Button>
              )}
            </Card>
            <div className="grid gap-4 md:grid-cols-2">
              {CONFIG_GROUPS.map(({ group, title }) => (
                <ConfigGroup
                  key={group}
                  title={title}
                  group={group}
                  config={config}
                  onChange={setField}
                />
              ))}
            </div>
          </div>
        )}

        <div className="fixed bottom-0 left-0 right-0 border-t border-border bg-surface/95 px-4 py-3 backdrop-blur">
          <div className="mx-auto flex max-w-4xl items-center justify-between gap-4">
            <span className="text-sm text-muted">
              {note ? (
                <span className="inline-flex items-center gap-1.5 text-success">
                  <CheckCircle size={15} weight="bold" /> {note}
                </span>
              ) : dirty ? (
                "Cambios sin guardar."
              ) : (
                "Moneda: MXN."
              )}
            </span>
            <Button variant="primary" onClick={save} disabled={busy || !dirty}>
              Guardar valores del taller
            </Button>
          </div>
        </div>

        {confirmReset && (
          <ConfirmDialog
            open
            title="Restablecer valores del taller"
            description="Los proyectos nuevos volverán a usar los valores del motor. Los proyectos existentes no cambian."
            confirmLabel="Restablecer"
            onCancel={() => setConfirmReset(false)}
            onConfirm={reset}
          />
        )}
      </main>
    </div>
  );
}

function NameCard({ auth }: { auth: AuthStatus }) {
  const [name, setName] = useState(auth.workspace?.name ?? "");
  const [saved, setSaved] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const result = await renameWorkspace(name.trim());
      setSaved(result.name);
    } catch (e) {
      setError(apiMessage(e, "No se pudo renombrar el taller."));
    }
  }

  return (
    <Card className="p-5">
      <SectionTitle sub="Aparece en la pantalla de entrada, en las invitaciones y en los reportes.">
        Nombre del taller
      </SectionTitle>
      {auth.mode === "open" ? (
        <p className="mt-2 text-sm text-muted">
          En modo local el taller se llama {auth.workspace?.name ?? "Taller"}. Activa las
          cuentas del taller para nombrarlo e invitar a tu equipo.
        </p>
      ) : (
        <form onSubmit={submit} className="mt-3 flex flex-col gap-2 sm:flex-row">
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={80}
            aria-label="Nombre del taller"
            className="flex-1"
          />
          <Button type="submit" variant="secondary" disabled={name.trim().length < 2 || name.trim() === (saved ?? auth.workspace?.name)}>
            Guardar nombre
          </Button>
        </form>
      )}
      {saved && <p className="mt-2 text-xs text-success">Ahora el taller se llama {saved}.</p>}
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </Card>
  );
}
