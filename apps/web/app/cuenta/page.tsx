"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  CheckCircle,
  DeviceMobile,
  GoogleLogo,
  SignOut,
  UsersThree,
  Warning,
} from "@phosphor-icons/react";
import { completeProfile } from "@/lib/identity";
import {
  apiMessage,
  changeEmail,
  changePassword,
  fetchAuthStatus,
  getMe,
  googleLoginUrl,
  listSessions,
  logout,
  logoutOthers,
  revokeSession,
  sendVerification,
  unlinkGoogle,
  updateMe,
  type AuthStatus,
  type AuthUser,
  type SessionInfo,
  type Workspace,
} from "@/lib/session";
import { describeAgent, timeAgo } from "@/lib/time";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import {
  Avatar,
  Badge,
  Button,
  buttonClasses,
  Callout,
  Card,
  Input,
  PageHeader,
  SectionTitle,
  SkeletonCards,
} from "@/components/ui";
import { WorkspaceHeader } from "@/components/WorkspaceHeader";

type Me = AuthUser & { workspace: Workspace | null; created_at: string };

export default function CuentaPage() {
  const router = useRouter();
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    getMe()
      .then(setMe)
      .catch(() => setError("No se pudo cargar tu cuenta."));
  }, []);

  useEffect(() => {
    let active = true;
    fetchAuthStatus().then((status) => {
      if (!active) return;
      if (!status.user) {
        router.replace("/bienvenida");
        return;
      }
      setAuth(status);
      reload();
    });
    return () => {
      active = false;
    };
  }, [reload, router]);

  async function signOut() {
    await logout();
    window.location.href = "/bienvenida";
  }

  return (
    <div className="min-h-screen">
      <WorkspaceHeader active="cuenta" />
      <main className="mx-auto max-w-3xl px-5 py-8 sm:px-6">
        <PageHeader
          title="Tu cuenta"
          sub="Perfil, acceso y sesiones. Lo que cambies aquí aplica en todos tus dispositivos."
          actions={
            <Button variant="ghost" size="sm" onClick={signOut}>
              <SignOut size={14} weight="bold" /> Cerrar sesión
            </Button>
          }
        />
        {error && (
          <div className="mb-4">
            <Callout tone="danger">{error}</Callout>
          </div>
        )}
        {me === null || auth === null ? (
          <SkeletonCards count={3} />
        ) : (
          <div className="space-y-4">
            <ProfileCard me={me} auth={auth} onChanged={reload} />
            <AccessCard me={me} auth={auth} onChanged={reload} />
            <SessionsCard />
            <WorkspaceCard me={me} />
          </div>
        )}
      </main>
    </div>
  );
}

/* ---------------------------------------------------------------- profile -- */

function ProfileCard({
  me,
  auth,
  onChanged,
}: {
  me: Me;
  auth: AuthStatus;
  onChanged: () => void;
}) {
  const [name, setName] = useState(me.name);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [verifyNote, setVerifyNote] = useState<string | null>(null);
  const [changing, setChanging] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [emailError, setEmailError] = useState<string | null>(null);

  async function saveName(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const updated = await updateMe(name.trim());
      completeProfile(updated.name);
      setMessage("Nombre actualizado.");
      onChanged();
    } catch (e) {
      setMessage(apiMessage(e, "No se pudo guardar el nombre."));
    } finally {
      setSaving(false);
    }
  }

  async function resend() {
    setVerifyNote(null);
    try {
      const result = await sendVerification();
      setVerifyNote(
        result.already_verified
          ? "Tu correo ya está verificado."
          : result.delivered
            ? "Te reenviamos el enlace de confirmación."
            : "Sin envío de correos configurado: pide el enlace a un administrador.",
      );
    } catch (e) {
      setVerifyNote(apiMessage(e, "No se pudo reenviar la confirmación."));
    }
  }

  async function submitEmail(event: FormEvent) {
    event.preventDefault();
    setEmailError(null);
    try {
      const result = await changeEmail(newEmail.trim(), currentPassword);
      setChanging(false);
      setNewEmail("");
      setCurrentPassword("");
      setVerifyNote(
        result.delivered
          ? `Enviamos un enlace a ${result.pending_email}; el cambio aplica al confirmarlo.`
          : `No pudimos enviar el correo a ${result.pending_email}. Inténtalo más tarde.`,
      );
      onChanged();
    } catch (e) {
      setEmailError(apiMessage(e, "No se pudo iniciar el cambio de correo."));
    }
  }

  return (
    <Card className="p-5">
      <SectionTitle>Perfil</SectionTitle>
      <div className="mt-3 flex items-start gap-4">
        <Avatar name={me.name} src={me.picture} self size="md" />
        <div className="min-w-0 flex-1 space-y-4">
          <form onSubmit={saveName} className="flex flex-col gap-2 sm:flex-row">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={80}
              aria-label="Nombre"
              className="flex-1"
            />
            <Button type="submit" variant="secondary" disabled={saving || name.trim() === me.name}>
              Guardar
            </Button>
          </form>
          {message && <p className="text-xs text-muted">{message}</p>}

          <div>
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-medium">{me.email}</span>
              {me.email_verified ? (
                <Badge tone="success">
                  <CheckCircle size={12} weight="bold" /> Verificado
                </Badge>
              ) : (
                <Badge tone="warning">
                  <Warning size={12} weight="bold" /> Sin verificar
                </Badge>
              )}
            </div>
            {me.pending_email && (
              <p className="mt-1 text-xs text-muted">
                Cambio pendiente a <span className="font-medium text-foreground">{me.pending_email}</span>{" "}
                hasta que lo confirmes desde ese correo.
              </p>
            )}
            <div className="mt-2 flex flex-wrap gap-2">
              {!me.email_verified && (
                <Button size="sm" variant="ghost" onClick={resend}>
                  Reenviar confirmación
                </Button>
              )}
              {auth.mail_enabled ? (
                <Button size="sm" variant="ghost" onClick={() => setChanging((v) => !v)}>
                  {changing ? "Cancelar" : "Cambiar correo"}
                </Button>
              ) : (
                <span className="self-center text-xs text-faint">
                  Cambiar el correo requiere envío de correos configurado.
                </span>
              )}
            </div>
            {verifyNote && <p className="mt-2 text-xs text-muted">{verifyNote}</p>}
            {changing && (
              <form onSubmit={submitEmail} className="mt-3 space-y-2 rounded-lg border border-border bg-surface-2/50 p-3">
                <Input
                  type="email"
                  value={newEmail}
                  onChange={(e) => setNewEmail(e.target.value)}
                  placeholder="Nuevo correo"
                  required
                  className="w-full"
                />
                {me.has_password && (
                  <Input
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    placeholder="Tu contraseña actual"
                    required
                    className="w-full"
                  />
                )}
                {emailError && <p className="text-xs text-danger">{emailError}</p>}
                <Button type="submit" size="sm" variant="secondary">
                  Enviar confirmación al nuevo correo
                </Button>
              </form>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ----------------------------------------------------------------- access -- */

function AccessCard({
  me,
  auth,
  onChanged,
}: {
  me: Me;
  auth: AuthStatus;
  onChanged: () => void;
}) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmUnlink, setConfirmUnlink] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNote(null);
    try {
      const result = await changePassword(current, next);
      setNote(
        result.sessions_revoked > 0
          ? `Contraseña actualizada; cerramos ${result.sessions_revoked} sesión(es) más.`
          : "Contraseña actualizada.",
      );
      setCurrent("");
      setNext("");
      onChanged();
    } catch (e) {
      setError(apiMessage(e, "No se pudo cambiar la contraseña."));
    }
  }

  async function doUnlink() {
    setConfirmUnlink(false);
    try {
      await unlinkGoogle();
      onChanged();
    } catch (e) {
      setError(apiMessage(e, "No se pudo desvincular Google."));
    }
  }

  return (
    <Card className="p-5">
      <SectionTitle sub="Al cambiar la contraseña cerramos tus otras sesiones; esta sigue abierta.">
        Acceso
      </SectionTitle>
      <form onSubmit={submit} className="mt-3 flex flex-wrap items-center gap-2">
        {me.has_password && (
          <Input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            placeholder="Contraseña actual"
            required
            className="min-w-48 flex-1"
          />
        )}
        <Input
          type="password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
          placeholder={me.has_password ? "Nueva contraseña (mín. 8)" : "Define una contraseña (mín. 8)"}
          minLength={8}
          required
          className="min-w-48 flex-1"
        />
        <Button type="submit" variant="secondary">
          {me.has_password ? "Cambiar" : "Guardar"}
        </Button>
      </form>
      {note && <p className="mt-2 text-xs text-success">{note}</p>}
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}

      {auth.google_enabled && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
          <div className="flex items-center gap-2 text-sm">
            <GoogleLogo size={16} weight="bold" />
            {me.has_google ? "Google vinculado a esta cuenta" : "Google no vinculado"}
          </div>
          {me.has_google ? (
            <Button
              size="sm"
              variant="ghost"
              disabled={!me.has_password}
              title={me.has_password ? undefined : "Define una contraseña antes de desvincular"}
              onClick={() => setConfirmUnlink(true)}
            >
              Desvincular
            </Button>
          ) : (
            <a href={googleLoginUrl()} className={buttonClasses("secondary", "sm")}>
              Vincular Google
            </a>
          )}
        </div>
      )}
      {confirmUnlink && (
        <ConfirmDialog
          open
          title="Desvincular Google"
          description="Dejarás de poder entrar con Google; seguirás entrando con tu contraseña."
          confirmLabel="Desvincular"
          onCancel={() => setConfirmUnlink(false)}
          onConfirm={doUnlink}
        />
      )}
    </Card>
  );
}

/* --------------------------------------------------------------- sessions -- */

function SessionsCard() {
  const [sessions, setSessions] = useState<SessionInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    listSessions()
      .then(setSessions)
      .catch(() => setError("No se pudieron cargar las sesiones."));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function revoke(session: SessionInfo) {
    try {
      await revokeSession(session.session_id);
      reload();
    } catch {
      setError("No se pudo cerrar la sesión.");
    }
  }

  async function closeOthers() {
    try {
      await logoutOthers();
      reload();
    } catch {
      setError("No se pudieron cerrar las demás sesiones.");
    }
  }

  const others = sessions?.filter((s) => !s.current) ?? [];

  return (
    <Card className="overflow-hidden">
      <div className="flex items-center justify-between gap-3 px-5 pt-5 pb-3">
        <SectionTitle sub="Dónde está abierta tu cuenta. Cierra lo que no reconozcas.">
          Sesiones
        </SectionTitle>
        {others.length > 0 && (
          <Button size="sm" variant="ghost" onClick={closeOthers}>
            Cerrar las demás
          </Button>
        )}
      </div>
      {error && (
        <div className="px-5 pb-3">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}
      {sessions === null ? (
        <div className="px-5 pb-5">
          <SkeletonCards count={2} />
        </div>
      ) : (
        <ul className="divide-y divide-border border-t border-border">
          {sessions.map((session) => (
            <li key={session.session_id} className="flex items-center gap-3 px-5 py-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-2 text-foreground">
                <DeviceMobile size={16} weight="duotone" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-medium">{describeAgent(session.user_agent)}</span>
                  {session.current && <Badge tone="accent">Esta sesión</Badge>}
                  {session.remember && <Badge>30 días</Badge>}
                </div>
                <div className="text-xs text-muted">
                  Última actividad {timeAgo(session.last_seen_at)}
                  {session.ip ? ` · ${session.ip}` : ""}
                </div>
              </div>
              {!session.current && (
                <Button size="sm" variant="ghost" onClick={() => revoke(session)}>
                  Cerrar
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/* -------------------------------------------------------------- workspace -- */

function WorkspaceCard({ me }: { me: Me }) {
  return (
    <Card className="flex flex-wrap items-center justify-between gap-3 p-5">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-surface-2 text-foreground">
          <UsersThree size={18} weight="duotone" />
        </span>
        <div>
          <div className="text-sm font-medium">{me.workspace?.name ?? "Taller"}</div>
          <div className="text-xs text-muted">
            {me.role === "admin" ? "Administras este taller" : "Miembro del taller"} · desde{" "}
            {timeAgo(me.created_at)}
          </div>
        </div>
      </div>
      {me.role === "admin" && (
        <Link href="/equipo" className={buttonClasses("secondary", "sm")}>
          Administrar equipo
        </Link>
      )}
    </Card>
  );
}
