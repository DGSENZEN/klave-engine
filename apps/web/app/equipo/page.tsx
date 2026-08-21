"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft, Check, Prohibit, UsersThree } from "@phosphor-icons/react";
import {
  fetchAuthStatus,
  listWorkspaceUsers,
  setUserRole,
  setUserStatus,
  type AuthUser,
  type WorkspaceUser,
} from "@/lib/session";
import {
  Avatar,
  Badge,
  Button,
  Callout,
  Card,
  EmptyState,
  PageHeader,
  SkeletonCards,
  type BadgeTone,
} from "@/components/ui";
import { ThemeToggle } from "@/components/ThemeToggle";

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

export default function EquipoPage() {
  const router = useRouter();
  const [me, setMe] = useState<AuthUser | null>(null);
  const [users, setUsers] = useState<WorkspaceUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    listWorkspaceUsers()
      .then(setUsers)
      .catch(() => setError("No se pudo cargar el equipo."));
  }, []);

  useEffect(() => {
    let active = true;
    fetchAuthStatus().then((status) => {
      if (!active) return;
      if (!status.user || status.user.role !== "admin") {
        router.replace("/");
        return;
      }
      setMe(status.user);
      reload();
    });
    return () => {
      active = false;
    };
  }, [reload, router]);

  async function approve(user: WorkspaceUser) {
    try {
      await setUserStatus(user.user_id, "active");
      reload();
    } catch {
      setError(`No se pudo aprobar a ${user.name}.`);
    }
  }

  async function toggleDisabled(user: WorkspaceUser) {
    try {
      await setUserStatus(user.user_id, user.status === "disabled" ? "active" : "disabled");
      reload();
    } catch {
      setError(`No se pudo actualizar a ${user.name}.`);
    }
  }

  async function changeRole(user: WorkspaceUser, role: "admin" | "member") {
    try {
      await setUserRole(user.user_id, role);
      reload();
    } catch {
      setError(`No se pudo cambiar el rol de ${user.name}.`);
    }
  }

  const pending = users?.filter((u) => u.status === "pending") ?? [];
  const rest = users?.filter((u) => u.status !== "pending") ?? [];

  return (
    <div className="mx-auto max-w-3xl px-5 py-8 sm:px-6">
      <div className="mb-6 flex items-center justify-between">
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-xs font-medium text-muted transition hover:text-foreground"
        >
          <ArrowLeft size={13} weight="bold" /> Proyectos
        </Link>
        <ThemeToggle />
      </div>

      <PageHeader
        title="Equipo del taller"
        sub="Aprueba cuentas nuevas, asigna roles y deshabilita accesos. El acceso a cada proyecto se administra desde su configuración."
      />

      {error && (
        <div className="mb-4">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}

      {users === null ? (
        <SkeletonCards count={3} />
      ) : users.length === 0 ? (
        <EmptyState
          icon={<UsersThree size={22} weight="duotone" />}
          title="Sin cuentas todavía"
          hint="Comparte la dirección de la app; cada registro aparecerá aquí para tu aprobación."
        />
      ) : (
        <>
          {pending.length > 0 && (
            <Card className="mb-4 overflow-hidden border-warning/40">
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
                    <Button size="sm" variant="primary" onClick={() => approve(user)}>
                      <Check size={14} weight="bold" /> Aprobar
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => toggleDisabled(user)}>
                      <Prohibit size={14} weight="bold" /> Rechazar
                    </Button>
                  </UserRow>
                ))}
              </ul>
            </Card>
          )}

          <Card className="overflow-hidden">
            <ul className="divide-y divide-border">
              {rest.map((user) => (
                <UserRow key={user.user_id} user={user} me={me}>
                  <select
                    value={user.role}
                    disabled={user.user_id === me?.user_id}
                    onChange={(e) => changeRole(user, e.target.value as "admin" | "member")}
                    className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm disabled:opacity-50"
                  >
                    <option value="member">Miembro</option>
                    <option value="admin">Admin</option>
                  </select>
                  {user.user_id !== me?.user_id && (
                    <Button size="sm" variant="ghost" onClick={() => toggleDisabled(user)}>
                      {user.status === "disabled" ? "Habilitar" : "Deshabilitar"}
                    </Button>
                  )}
                </UserRow>
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  );
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
        </div>
        <div className="truncate text-xs text-muted">{user.email}</div>
      </div>
      <Badge tone={STATUS_TONES[user.status] ?? "default"}>
        {STATUS_LABELS[user.status] ?? user.status}
      </Badge>
      <div className="flex shrink-0 items-center gap-2">{children}</div>
    </li>
  );
}
