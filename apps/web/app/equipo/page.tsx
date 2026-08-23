"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  Check,
  ClockCounterClockwise,
  Copy,
  EnvelopeSimple,
  Key,
  PaperPlaneTilt,
  Prohibit,
  UserPlus,
  UsersThree,
} from "@phosphor-icons/react";
import { listProjects, type ProjectSummary } from "@/lib/api";
import {
  apiMessage,
  createInvitation,
  fetchAuthStatus,
  issueRecoveryLink,
  listAudit,
  listInvitations,
  listWorkspaceUsers,
  resendInvitation,
  revokeInvitation,
  setUserRole,
  setUserStatus,
  type AuditEntry,
  type AuthStatus,
  type AuthUser,
  type Invitation,
  type ProjectGrant,
  type WorkspaceUser,
} from "@/lib/session";
import { formatDateTime, timeAgo } from "@/lib/time";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Modal } from "@/components/Modal";
import { KebabMenu, MenuItem } from "@/components/Menu";
import {
  Avatar,
  Badge,
  Button,
  Callout,
  Card,
  Checkbox,
  EmptyState,
  Input,
  PageHeader,
  Select,
  SkeletonCards,
  type BadgeTone,
} from "@/components/ui";
import { WorkspaceHeader } from "@/components/WorkspaceHeader";

const STATUS_LABELS: Record<string, string> = {
  pending: "Pendiente",
  active: "Activa",
  disabled: "Deshabilitada",
};

const STATUS_TONES: Record<string, BadgeTone> = {
  pending: "warning",
  active: "success",
  disabled: "danger",
};

const INVITE_STATE: Record<Invitation["state"], { label: string; tone: BadgeTone }> = {
  open: { label: "Abierta", tone: "accent" },
  accepted: { label: "Aceptada", tone: "success" },
  revoked: { label: "Revocada", tone: "danger" },
  expired: { label: "Caducada", tone: "warning" },
};

const AUDIT_LABELS: Record<string, string> = {
  invitation_created: "invitó a",
  invitation_resent: "reenvió la invitación a",
  invitation_revoked: "revocó la invitación de",
  invitation_accepted: "aceptó su invitación",
  user_status_changed: "cambió el estado de",
  user_role_changed: "cambió el rol de",
  recovery_link_issued: "generó un enlace de recuperación para",
  password_reset: "restableció su contraseña",
  password_reset_requested: "pidió restablecer su contraseña",
  password_changed: "cambió su contraseña",
  email_changed: "cambió su correo",
  google_unlinked: "desvinculó Google",
  project_access_granted: "compartió un proyecto con",
  project_access_revoked: "quitó acceso a un proyecto",
  project_removed: "quitó un proyecto de la lista",
};

type Confirm =
  | { kind: "role"; user: WorkspaceUser; role: "admin" | "member" }
  | { kind: "disable"; user: WorkspaceUser }
  | { kind: "reject"; user: WorkspaceUser }
  | { kind: "recovery"; user: WorkspaceUser }
  | { kind: "revoke_invite"; invite: Invitation };

export default function EquipoPage() {
  const router = useRouter();
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [users, setUsers] = useState<WorkspaceUser[] | null>(null);
  const [invitations, setInvitations] = useState<Invitation[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  const [issuedLink, setIssuedLink] = useState<{ email: string; link: string; hours: number } | null>(
    null,
  );
  // Authority changes go through a deliberate confirmation, never a misclick.
  const [confirm, setConfirm] = useState<Confirm | null>(null);

  const reload = useCallback(() => {
    listWorkspaceUsers()
      .then(setUsers)
      .catch(() => setError("No se pudo cargar el equipo."));
    listInvitations()
      .then(setInvitations)
      .catch(() => setInvitations([]));
  }, []);

  useEffect(() => {
    let active = true;
    fetchAuthStatus().then((status) => {
      if (!active) return;
      if (!status.user || status.user.role !== "admin") {
        router.replace("/");
        return;
      }
      setAuth(status);
      reload();
    });
    return () => {
      active = false;
    };
  }, [reload, router]);

  const me = auth?.user ?? null;

  async function run(action: () => Promise<unknown>, failure: string) {
    try {
      await action();
      reload();
    } catch (e) {
      setError(apiMessage(e, failure));
    }
  }

  async function issueRecovery(user: WorkspaceUser) {
    try {
      const result = await issueRecoveryLink(user.user_id);
      setIssuedLink({ email: result.email, link: result.link, hours: result.expires_in_hours });
      reload();
    } catch (e) {
      setError(apiMessage(e, `No se pudo generar el enlace para ${user.name}.`));
    }
  }

  const pending = users?.filter((u) => u.status === "pending") ?? [];
  const rest = users?.filter((u) => u.status !== "pending") ?? [];
  const openInvites = invitations?.filter((i) => i.state === "open" || i.state === "expired") ?? [];

  return (
    <div className="min-h-screen">
      <WorkspaceHeader active="equipo" />
      <main className="mx-auto max-w-3xl px-5 py-8 sm:px-6">
        <PageHeader
          title={auth?.workspace ? `Equipo de ${auth.workspace.name}` : "Equipo del taller"}
          sub="Invita, aprueba, asigna roles y recupera accesos. El acceso a cada proyecto se administra desde su configuración."
          actions={
            <Button variant="primary" onClick={() => setInviting(true)}>
              <UserPlus size={15} weight="bold" /> Invitar
            </Button>
          }
        />

        {auth && !auth.mail_enabled && (
          <div className="mb-4">
            <Callout tone="info">
              Sin envío de correos configurado: las invitaciones y los enlaces de recuperación
              se muestran aquí para que los entregues tú (WhatsApp, en persona). Configura
              <code className="mx-1 font-mono text-xs">KLAVE_SMTP_HOST</code> o
              <code className="mx-1 font-mono text-xs">KLAVE_RESEND_API_KEY</code> para
              enviarlos automáticamente.
            </Callout>
          </div>
        )}
        {error && (
          <div className="mb-4">
            <Callout tone="danger">{error}</Callout>
          </div>
        )}
        {issuedLink && (
          <div className="mb-4">
            <LinkPanel
              title={`Enlace de recuperación para ${issuedLink.email}`}
              hint={`Vale ${issuedLink.hours} horas y se usa una sola vez. Entrégalo solo a esa persona.`}
              link={issuedLink.link}
              onClose={() => setIssuedLink(null)}
            />
          </div>
        )}

        {users === null ? (
          <SkeletonCards count={3} />
        ) : (
          <div className="space-y-4">
            {pending.length > 0 && (
              <Card className="overflow-hidden border-warning/40">
                <div className="border-b border-border bg-warning-soft/60 px-5 py-3">
                  <span className="text-sm font-medium text-warning">
                    {pending.length === 1
                      ? "1 cuenta espera tu aprobación"
                      : `${pending.length} cuentas esperan tu aprobación`}
                  </span>
                </div>
                <ul className="divide-y divide-border">
                  {pending.map((user) => (
                    <UserRow key={user.user_id} user={user} me={me}>
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={() =>
                          run(() => setUserStatus(user.user_id, "active"), `No se pudo aprobar a ${user.name}.`)
                        }
                      >
                        <Check size={14} weight="bold" /> Aprobar
                      </Button>
                      <Button size="sm" variant="danger" onClick={() => setConfirm({ kind: "reject", user })}>
                        <Prohibit size={14} weight="bold" /> Rechazar
                      </Button>
                    </UserRow>
                  ))}
                </ul>
              </Card>
            )}

            {openInvites.length > 0 && (
              <InvitationsCard
                invitations={openInvites}
                onRevoke={(invite) => setConfirm({ kind: "revoke_invite", invite })}
                onResent={(email, link) => setIssuedLink({ email, link, hours: 24 * 7 })}
                onError={setError}
                onChanged={reload}
              />
            )}

            {users.length === 0 ? (
              <EmptyState
                icon={<UsersThree size={22} weight="duotone" />}
                title="Sin cuentas todavía"
                hint="Invita a tu equipo; cada persona entra con su propio enlace."
              />
            ) : (
              <Card className="overflow-hidden">
                <ul className="divide-y divide-border">
                  {rest.map((user) => (
                    <UserRow key={user.user_id} user={user} me={me}>
                      <Select
                        value={user.role}
                        disabled={user.user_id === me?.user_id}
                        onChange={(e) =>
                          setConfirm({ kind: "role", user, role: e.target.value as "admin" | "member" })
                        }
                      >
                        <option value="member">Miembro</option>
                        <option value="admin">Admin</option>
                      </Select>
                      {user.user_id !== me?.user_id && (
                        <KebabMenu label={`Acciones para ${user.name}`}>
                          {(close) => (
                            <>
                              <MenuItem
                                onSelect={() => {
                                  close();
                                  setConfirm({ kind: "recovery", user });
                                }}
                              >
                                <Key size={14} weight="bold" /> Enlace de recuperación
                              </MenuItem>
                              {user.status === "disabled" ? (
                                <MenuItem
                                  onSelect={() => {
                                    close();
                                    run(
                                      () => setUserStatus(user.user_id, "active"),
                                      `No se pudo habilitar a ${user.name}.`,
                                    );
                                  }}
                                >
                                  <Check size={14} weight="bold" /> Habilitar
                                </MenuItem>
                              ) : (
                                <MenuItem
                                  danger
                                  onSelect={() => {
                                    close();
                                    setConfirm({ kind: "disable", user });
                                  }}
                                >
                                  <Prohibit size={14} weight="bold" /> Deshabilitar
                                </MenuItem>
                              )}
                            </>
                          )}
                        </KebabMenu>
                      )}
                    </UserRow>
                  ))}
                </ul>
              </Card>
            )}

            <ActivityCard />
          </div>
        )}

        {inviting && auth && (
          <InviteDialog
            mailEnabled={auth.mail_enabled}
            onClose={() => setInviting(false)}
            onCreated={reload}
          />
        )}

        {confirm && (
          <ConfirmDialog
            open
            title={confirmTitle(confirm)}
            description={confirmDescription(confirm)}
            confirmLabel={confirmLabel(confirm)}
            onCancel={() => setConfirm(null)}
            onConfirm={() => {
              const action = confirm;
              setConfirm(null);
              if (action.kind === "role") {
                run(
                  () => setUserRole(action.user.user_id, action.role),
                  `No se pudo cambiar el rol de ${action.user.name}.`,
                );
              } else if (action.kind === "recovery") {
                issueRecovery(action.user);
              } else if (action.kind === "revoke_invite") {
                run(() => revokeInvitation(action.invite.invite_id), "No se pudo revocar la invitación.");
              } else {
                run(
                  () => setUserStatus(action.user.user_id, "disabled"),
                  `No se pudo actualizar a ${action.user.name}.`,
                );
              }
            }}
          />
        )}
      </main>
    </div>
  );
}

function confirmTitle(confirm: Confirm): string {
  switch (confirm.kind) {
    case "role":
      return confirm.role === "admin" ? "Otorgar rol de administrador" : "Quitar rol de administrador";
    case "disable":
      return "Deshabilitar cuenta";
    case "reject":
      return "Rechazar solicitud";
    case "recovery":
      return "Generar enlace de recuperación";
    case "revoke_invite":
      return "Revocar invitación";
  }
}

function confirmLabel(confirm: Confirm): string {
  switch (confirm.kind) {
    case "role":
      return "Cambiar rol";
    case "disable":
      return "Deshabilitar";
    case "reject":
      return "Rechazar";
    case "recovery":
      return "Generar enlace";
    case "revoke_invite":
      return "Revocar";
  }
}

function confirmDescription(confirm: Confirm) {
  const name = (value: string) => <span className="font-medium text-foreground">{value}</span>;
  switch (confirm.kind) {
    case "role":
      return confirm.role === "admin" ? (
        <>{name(confirm.user.name)} podrá invitar y aprobar cuentas, ver todos los proyectos y administrar el taller.</>
      ) : (
        <>{name(confirm.user.name)} dejará de administrar el taller y solo verá los proyectos que se le compartan.</>
      );
    case "disable":
    case "reject":
      return (
        <>
          {name(confirm.user.name)} ({confirm.user.email}) perderá el acceso al taller y sus sesiones
          se cerrarán, hasta que vuelvas a habilitarla.
        </>
      );
    case "recovery":
      return (
        <>
          Se generará un enlace que permite a {name(confirm.user.name)} elegir una contraseña nueva sin
          conocer la anterior. Entrégaselo solo a esa persona; queda registrado en la actividad.
        </>
      );
    case "revoke_invite":
      return <>{name(confirm.invite.email)} ya no podrá usar su enlace. Podrás invitar de nuevo.</>;
  }
}

function UserRow({
  user,
  me,
  children,
}: {
  user: WorkspaceUser;
  me: AuthUser | null;
  children: React.ReactNode;
}) {
  return (
    <li className="flex items-center gap-3 px-5 py-3.5">
      <Avatar name={user.name} src={user.picture} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{user.name}</span>
          {user.user_id === me?.user_id && <span className="text-xs text-faint">(tú)</span>}
          {!user.email_verified && user.status === "active" && (
            <span className="text-xs text-faint" title="Correo sin verificar">
              · sin verificar
            </span>
          )}
        </div>
        <div className="truncate text-xs text-muted">{user.email}</div>
      </div>
      <Badge tone={STATUS_TONES[user.status] ?? "default"}>{STATUS_LABELS[user.status] ?? user.status}</Badge>
      <div className="flex shrink-0 items-center gap-2">{children}</div>
    </li>
  );
}

/* ------------------------------------------------------------ invitations -- */

function InvitationsCard({
  invitations,
  onRevoke,
  onResent,
  onError,
  onChanged,
}: {
  invitations: Invitation[];
  onRevoke: (invite: Invitation) => void;
  onResent: (email: string, link: string) => void;
  onError: (message: string) => void;
  onChanged: () => void;
}) {
  async function resend(invite: Invitation) {
    try {
      const result = await resendInvitation(invite.invite_id);
      onResent(invite.email, result.link);
      onChanged();
    } catch (e) {
      onError(apiMessage(e, "No se pudo reenviar la invitación."));
    }
  }

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center gap-2 border-b border-border px-5 py-3">
        <EnvelopeSimple size={16} weight="duotone" className="text-muted" />
        <span className="text-sm font-medium">
          {invitations.length === 1 ? "1 invitación" : `${invitations.length} invitaciones`} sin aceptar
        </span>
      </div>
      <ul className="divide-y divide-border">
        {invitations.map((invite) => (
          <li key={invite.invite_id} className="flex items-center gap-3 px-5 py-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="truncate font-medium">{invite.email}</span>
                <Badge tone={invite.role === "admin" ? "accent" : "default"}>
                  {invite.role === "admin" ? "Admin" : "Miembro"}
                </Badge>
                <Badge tone={INVITE_STATE[invite.state].tone}>{INVITE_STATE[invite.state].label}</Badge>
              </div>
              <div className="text-xs text-muted">
                {invite.inviter_name ? `Invitó ${invite.inviter_name} · ` : ""}
                {invite.state === "expired" ? "caducó" : "caduca"} {formatDateTime(invite.expires_at)}
                {invite.project_grants.length > 0 &&
                  ` · ${invite.project_grants.length} proyecto${invite.project_grants.length === 1 ? "" : "s"}`}
              </div>
            </div>
            <Button size="sm" variant="ghost" onClick={() => resend(invite)}>
              <PaperPlaneTilt size={14} weight="bold" /> Reenviar
            </Button>
            <Button size="sm" variant="ghost" onClick={() => onRevoke(invite)}>
              Revocar
            </Button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function InviteDialog({
  mailEnabled,
  onClose,
  onCreated,
}: {
  mailEnabled: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"admin" | "member">("member");
  const [projects, setProjects] = useState<ProjectSummary[] | null>(null);
  const [grants, setGrants] = useState<Record<string, ProjectGrant["role"] | undefined>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ email: string; link: string; delivered: boolean } | null>(null);

  useEffect(() => {
    let active = true;
    listProjects()
      .then((items) => active && setProjects(items.filter((p) => !p.archived)))
      .catch(() => active && setProjects([]));
    return () => {
      active = false;
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const projectGrants: ProjectGrant[] = Object.entries(grants)
        .filter((entry): entry is [string, ProjectGrant["role"]] => Boolean(entry[1]))
        .map(([project_id, grantRole]) => ({ project_id, role: grantRole }));
      const created = await createInvitation(email.trim(), role, projectGrants);
      setResult({ email: created.email, link: created.link, delivered: created.delivered });
      onCreated();
    } catch (e) {
      setError(apiMessage(e, "No se pudo crear la invitación."));
    } finally {
      setBusy(false);
    }
  }

  const formId = "invitar-al-taller";
  return (
    <Modal
      open
      busy={busy}
      onClose={onClose}
      size="lg"
      title={result ? (result.delivered ? "Invitación enviada" : "Invitación lista") : "Invitar al taller"}
      sub={
        result
          ? result.delivered
            ? `Le enviamos el enlace a ${result.email}. También puedes compartirlo tú:`
            : `Sin correo configurado: comparte este enlace con ${result.email}. Vale siete días.`
          : `La persona entra de inmediato con su propio enlace; no necesita aprobación.${
              !mailEnabled ? " Sin correo configurado, el enlace se te mostrará para compartirlo." : ""
            }`
      }
      footer={
        result ? (
          <>
            <Button variant="secondary" onClick={() => { setResult(null); setEmail(""); setGrants({}); }}>
              Invitar a alguien más
            </Button>
            <Button variant="primary" onClick={onClose}>
              Listo
            </Button>
          </>
        ) : (
          <>
            <Button variant="secondary" onClick={onClose} disabled={busy}>
              Cancelar
            </Button>
            <Button type="submit" form={formId} variant="primary" disabled={busy}>
              <PaperPlaneTilt size={14} weight="bold" /> {busy ? "Invitando…" : "Invitar"}
            </Button>
          </>
        )
      }
    >
        {result ? (
          <LinkPanel link={result.link} />
        ) : (
          <form id={formId} onSubmit={submit} className="space-y-4">
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="correo@taller.mx"
                autoFocus
                required
                className="flex-1"
              />
              <Select
                value={role}
                onChange={(e) => setRole(e.target.value as "admin" | "member")}
              >
                <option value="member">Miembro</option>
                <option value="admin">Administrador</option>
              </Select>
            </div>
            {role === "admin" && (
              <Callout tone="warning">
                Un administrador ve todos los proyectos, invita y aprueba cuentas. Úsalo con
                criterio.
              </Callout>
            )}
            <div>
              <div className="microlabel mb-2">Acceso a proyectos (opcional)</div>
              {projects === null ? (
                <div className="text-xs text-muted">Cargando proyectos…</div>
              ) : projects.length === 0 ? (
                <div className="text-xs text-muted">Aún no hay proyectos; podrás compartirlos después.</div>
              ) : (
                <ul className="max-h-48 divide-y divide-border overflow-y-auto rounded-lg border border-border">
                  {projects.map((project) => {
                    const selected = grants[project.project_id];
                    return (
                      <li key={project.project_id} className="flex items-center gap-3 px-3 py-2">
                        <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-sm">
                          <Checkbox
                            checked={Boolean(selected)}
                            onChange={(e) =>
                              setGrants((g) => ({
                                ...g,
                                [project.project_id]: e.target.checked ? "viewer" : undefined,
                              }))
                            }
                          />
                          <span className="truncate">{project.name}</span>
                        </label>
                        {selected && (
                          <Select
                            value={selected}
                            onChange={(e) =>
                              setGrants((g) => ({
                                ...g,
                                [project.project_id]: e.target.value as ProjectGrant["role"],
                              }))
                            }
                            size="sm"
                          >
                            <option value="viewer">Ver</option>
                            <option value="editor">Editar</option>
                            <option value="owner">Propietario</option>
                          </Select>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
            {error && <p className="text-sm text-danger">{error}</p>}
          </form>
        )}
    </Modal>
  );
}

function LinkPanel({
  title,
  hint,
  link,
  onClose,
}: {
  title?: string;
  hint?: string;
  link: string;
  onClose?: () => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      window.prompt("Copia el enlace:", link);
    }
  }

  return (
    <div className="rounded-lg border border-border bg-surface-2/60 p-3">
      {title && <div className="text-sm font-medium">{title}</div>}
      {hint && <p className="mb-2 text-xs text-muted">{hint}</p>}
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded-md border border-border bg-surface px-2 py-1.5 font-mono text-xs">
          {link}
        </code>
        <Button size="sm" variant="secondary" onClick={copy}>
          <Copy size={14} weight="bold" /> {copied ? "Copiado" : "Copiar"}
        </Button>
        {onClose && (
          <Button size="sm" variant="ghost" onClick={onClose}>
            Ocultar
          </Button>
        )}
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- activity -- */

function ActivityCard() {
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);

  useEffect(() => {
    if (!open || entries !== null) return;
    let active = true;
    listAudit(60)
      .then((rows) => active && setEntries(rows))
      .catch(() => active && setEntries([]));
    return () => {
      active = false;
    };
  }, [open, entries]);

  return (
    <Card className="overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-5 py-3 text-left text-sm font-medium"
      >
        <ClockCounterClockwise size={16} weight="duotone" className="text-muted" />
        Registro de actividad
        <span className="ml-auto text-xs font-normal text-muted">{open ? "Ocultar" : "Ver"}</span>
      </button>
      {open &&
        (entries === null ? (
          <div className="px-5 pb-4 text-xs text-muted">Cargando…</div>
        ) : entries.length === 0 ? (
          <div className="border-t border-border px-5 py-4 text-xs text-muted">Sin actividad registrada.</div>
        ) : (
          <ul className="divide-y divide-border border-t border-border">
            {entries.map((entry) => {
              const email = typeof entry.detail.email === "string" ? entry.detail.email : null;
              const actor = entry.actor_name ?? "Sistema";
              const verb = AUDIT_LABELS[entry.action] ?? entry.action;
              const transition =
                typeof entry.detail.from === "string" && typeof entry.detail.to === "string"
                  ? ` (${entry.detail.from} → ${entry.detail.to})`
                  : typeof entry.detail.role === "string"
                    ? ` como ${entry.detail.role}`
                    : "";
              return (
                <li key={entry.audit_id} className="flex items-baseline gap-3 px-5 py-2.5 text-sm">
                  <span className="min-w-0 flex-1">
                    <span className="font-medium">{actor}</span> {verb}
                    {email && email !== entry.actor_name ? ` ${email}` : ""}
                    {transition}
                  </span>
                  <span className="shrink-0 text-xs text-muted" title={formatDateTime(entry.created_at)}>
                    {timeAgo(entry.created_at)}
                  </span>
                </li>
              );
            })}
          </ul>
        ))}
    </Card>
  );
}
