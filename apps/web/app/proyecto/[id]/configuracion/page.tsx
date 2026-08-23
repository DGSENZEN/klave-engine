"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Archive, ArrowCounterClockwise, Trash, UsersThree } from "@phosphor-icons/react";
import {
  ApiError,
  apiMessage,
  getProject,
  patchProject,
  removeProject,
  type ProjectInfo,
} from "@/lib/api";
import { getBrowserActor } from "@/lib/collab";
import {
  fetchAuthStatus,
  getProjectAccess,
  grantProjectAccess,
  revokeProjectAccess,
  type ProjectAccess,
  type ProjectMember,
} from "@/lib/session";
import {
  Avatar,
  Badge,
  Button,
  Callout,
  Card,
  Input,
  PageHeader,
  SectionTitle,
  Select,
  Skeleton,
  SkeletonHeader,
} from "@/components/ui";
import { ConfirmDialog } from "@/components/ConfirmDialog";

const PROJECT_ROLE_LABELS: Record<string, string> = {
  viewer: "Lectura",
  editor: "Edición",
  owner: "Propietario",
};

export default function ConfiguracionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [name, setName] = useState("");
  const [client, setClient] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [removeOpen, setRemoveOpen] = useState(false);
  const [protectedMode, setProtectedMode] = useState(false);

  useEffect(() => {
    let active = true;
    getProject(id)
      .then((info) => {
        if (!active) return;
        setProject(info);
        setName(info.project_name);
        setClient(info.client ?? "");
      })
      .catch(() => {
        if (active) setError("No se pudo cargar el proyecto.");
      });
    fetchAuthStatus().then((status) => {
      if (active) setProtectedMode(status.mode === "protected");
    });
    return () => {
      active = false;
    };
  }, [id]);

  async function save() {
    setError(null);
    setSaved(false);
    try {
      const result = await patchProject(
        id,
        { name: name.trim(), client: client.trim() },
        getBrowserActor(),
      );
      setProject((current) =>
        current
          ? { ...current, project_name: result.name, client: result.client }
          : current,
      );
      setSaved(true);
      window.setTimeout(() => setSaved(false), 4000);
    } catch {
      setError("No se pudieron guardar los cambios.");
    }
  }

  async function toggleArchived() {
    if (!project) return;
    try {
      const result = await patchProject(
        id,
        { archived: !project.archived },
        getBrowserActor(),
      );
      setProject({ ...project, archived: result.archived });
    } catch {
      setError("No se pudo archivar el proyecto.");
    }
  }

  async function remove() {
    try {
      await removeProject(id, getBrowserActor());
      router.replace("/");
    } catch {
      setError("No se pudo quitar el proyecto.");
    }
  }

  if (!project && error) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <PageHeader title="Configuración del proyecto" />
        <Callout tone="danger">{error}</Callout>
      </div>
    );
  }
  if (!project) {
    return (
      <div className="px-6 py-7 lg:px-8">
        <SkeletonHeader />
        <Skeleton className="h-64" />
      </div>
    );
  }

  return (
    <div className="rise-in mx-auto max-w-3xl px-6 py-7 lg:px-8">
      <PageHeader
        title="Configuración del proyecto"
        sub="Organización, acceso del equipo y acciones sobre este proyecto."
      />

      {error && (
        <div className="mb-4">
          <Callout tone="danger">{error}</Callout>
        </div>
      )}
      {saved && (
        <div className="mb-4" role="status">
          <Callout
            tone="info"
            action={
              <Button size="sm" variant="ghost" onClick={() => setSaved(false)}>
                Cerrar
              </Button>
            }
          >
            Nombre y cliente guardados.
          </Callout>
        </div>
      )}

      <Card className="mb-4 p-5">
        <SectionTitle>Organización</SectionTitle>
        <div className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-sm font-medium">Nombre del proyecto</span>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={80}
              className="w-full"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-sm font-medium">Cliente</span>
            <Input
              value={client}
              onChange={(e) => setClient(e.target.value)}
              placeholder="Nombre del cliente (opcional)"
              maxLength={80}
              className="w-full"
            />
          </label>
          <div className="flex justify-end">
            <Button variant="primary" onClick={save} disabled={!name.trim()}>
              Guardar
            </Button>
          </div>
        </div>
      </Card>

      {protectedMode && <AccessCard projectId={id} />}

      <Card className="p-5">
        <SectionTitle sub="Archivar lo oculta de la lista activa; quitarlo lo saca de la lista sin borrar archivos del disco.">
          Acciones
        </SectionTitle>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={toggleArchived}>
            {project.archived ? (
              <>
                <ArrowCounterClockwise size={15} weight="bold" /> Restaurar
              </>
            ) : (
              <>
                <Archive size={15} weight="bold" /> Archivar
              </>
            )}
          </Button>
          <Button variant="danger" onClick={() => setRemoveOpen(true)}>
            <Trash size={15} weight="bold" /> Quitar de la lista…
          </Button>
        </div>
      </Card>

      <ConfirmDialog
        open={removeOpen}
        title="Quitar proyecto de la lista"
        description={
          <>
            <span className="font-medium text-foreground">{project.project_name}</span>{" "}
            dejará de aparecer en el taller para todo el equipo. Los archivos y reportes
            permanecen en el disco.
          </>
        }
        confirmLabel="Quitar de la lista"
        typeToConfirm={project.project_name}
        onCancel={() => setRemoveOpen(false)}
        onConfirm={() => {
          setRemoveOpen(false);
          remove();
        }}
      />
    </div>
  );
}

function AccessCard({ projectId }: { projectId: string }) {
  const [access, setAccess] = useState<ProjectAccess | null>(null);
  const [forbidden, setForbidden] = useState(false);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"viewer" | "editor" | "owner">("editor");
  const [error, setError] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<ProjectMember | null>(null);

  const reload = useCallback(() => {
    getProjectAccess(projectId)
      .then((result) => {
        setAccess(result);
        setForbidden(false);
      })
      .catch((e) => {
        if (e instanceof ApiError && (e.status === 403 || e.status === 401)) {
          setForbidden(true);
        } else {
          setError("No se pudo cargar el acceso del proyecto.");
        }
      });
  }, [projectId]);

  useEffect(() => {
    reload();
  }, [reload]);

  async function grant() {
    if (!email.trim()) return;
    setError(null);
    try {
      await grantProjectAccess(projectId, email.trim(), role);
      setEmail("");
      reload();
    } catch (e) {
      setError(apiMessage(e, "No se pudo compartir el proyecto."));
    }
  }

  async function revoke(userId: string) {
    try {
      await revokeProjectAccess(projectId, userId);
      reload();
    } catch {
      setError("No se pudo quitar el acceso.");
    }
  }

  if (forbidden) {
    return (
      <Card className="mb-4 p-5">
        <SectionTitle>Acceso del equipo</SectionTitle>
        <p className="text-sm text-muted">
          Solo el propietario del proyecto o un administrador puede administrar el acceso.
        </p>
      </Card>
    );
  }

  return (
    <Card className="mb-4 p-5">
      <SectionTitle sub="Lectura ve los reportes; edición ajusta parámetros y revisiones; propietario comparte y configura.">
        Acceso del equipo
      </SectionTitle>
      {error && <p className="mb-3 text-sm text-danger">{error}</p>}
      {access === null ? (
        <Skeleton className="h-24" />
      ) : (
        <>
          {access.members.length === 0 ? (
            <p className="mb-4 flex items-center gap-2 text-sm text-muted">
              <UsersThree size={16} /> Nadie más tiene acceso todavía.
            </p>
          ) : (
            <ul className="mb-4 divide-y divide-border">
              {access.members.map((member) => (
                <li key={member.user_id} className="flex items-center gap-3 py-2.5">
                  <Avatar name={member.name} src={member.picture} size="sm" />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-medium">{member.name}</div>
                    <div className="truncate text-xs text-muted">{member.email}</div>
                  </div>
                  <Badge tone={member.project_role === "owner" ? "accent" : "default"}>
                    {PROJECT_ROLE_LABELS[member.project_role]}
                  </Badge>
                  <Button size="sm" variant="ghost" onClick={() => setRevokeTarget(member)}>
                    Quitar
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <Input
              list={`invitable-${projectId}`}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="correo@taller.mx"
              className="min-w-52 flex-1"
            />
            <datalist id={`invitable-${projectId}`}>
              {access.invitable.map((user) => (
                <option key={user.user_id} value={user.email}>
                  {user.name}
                </option>
              ))}
            </datalist>
            <Select
              value={role}
              onChange={(e) => setRole(e.target.value as typeof role)}
            >
              <option value="viewer">Lectura</option>
              <option value="editor">Edición</option>
              <option value="owner">Propietario</option>
            </Select>
            <Button variant="primary" onClick={grant} disabled={!email.trim()}>
              Compartir
            </Button>
          </div>
          <ConfirmDialog
            open={revokeTarget !== null}
            title="Quitar acceso al proyecto"
            description={
              revokeTarget ? (
                <>
                  <span className="font-medium text-foreground">{revokeTarget.name}</span> (
                  {revokeTarget.email}) dejará de ver y editar este proyecto.
                </>
              ) : null
            }
            confirmLabel="Quitar acceso"
            onCancel={() => setRevokeTarget(null)}
            onConfirm={() => {
              const target = revokeTarget;
              setRevokeTarget(null);
              if (target) revoke(target.user_id);
            }}
          />
        </>
      )}
    </Card>
  );
}
