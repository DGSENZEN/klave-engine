"use client";

import { API_MISCONFIGURED } from "@/lib/api";

/** Invalid explicit overrides should not masquerade as a service outage. */
export function ApiBaseWarning() {
  if (!API_MISCONFIGURED) return null;
  return (
    <div
      role="alert"
      className="bg-danger px-4 py-2 text-center text-sm font-medium text-white"
    >
      La dirección del servidor (NEXT_PUBLIC_API_URL) no es válida;
      revisa la configuración para cargar datos.
    </div>
  );
}
