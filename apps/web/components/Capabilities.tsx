"use client";

import { createContext, useContext, useSyncExternalStore, type ReactNode } from "react";
import { capabilities, type Capabilities, type LegacyRole, type ProjectRole } from "@/lib/capabilities";
import { authStatusSnapshot, subscribeAuthStatus } from "@/lib/session";

/** Inside a project: the viewer's role there (undefined while it loads). */
const ProjectRoleContext = createContext<{ role: ProjectRole | LegacyRole | undefined } | null>(null);

export function CapabilitiesProvider({
  projectRole,
  children,
}: {
  projectRole: ProjectRole | LegacyRole | undefined;
  children: ReactNode;
}) {
  return (
    <ProjectRoleContext.Provider value={{ role: projectRole }}>{children}</ProjectRoleContext.Provider>
  );
}

const NONE: Capabilities = {
  editCatalog: false,
  editProject: false,
  manageProject: false,
  approveGate: false,
};

/**
 * What this person may do here. Until the session (and, inside a project,
 * the project role) is known everything is false and `ready` is false, so a
 * control appears once known instead of flashing in and then vanishing.
 */
export function useCapabilities(
  /** Outside a project page (e.g. a row on Inicio): that project's role. */
  projectRoleOverride?: ProjectRole | LegacyRole,
): Capabilities & { ready: boolean } {
  const context = useContext(ProjectRoleContext);
  const project = projectRoleOverride !== undefined ? { role: projectRoleOverride } : context;
  const status = useSyncExternalStore(subscribeAuthStatus, authStatusSnapshot, () => null);
  if (!status || (project && project.role === undefined)) return { ...NONE, ready: false };
  return {
    ...capabilities({
      mode: status.mode,
      tallerRole: status.user?.role ?? null,
      projectRole: project?.role ?? null,
    }),
    ready: true,
  };
}
