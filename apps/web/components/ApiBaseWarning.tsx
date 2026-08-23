"use client";

import { API_MISCONFIGURED } from "@/lib/api";

/** Shown on every page of a production build that has no API URL configured. */
export function ApiBaseWarning() {
  if (!API_MISCONFIGURED) return null;
  return (
    <div
      role="alert"
      className="bg-danger px-4 py-2 text-center text-sm font-medium text-white"
    >
      Esta instalación no tiene configurada la dirección del servidor (NEXT_PUBLIC_API_URL);
      ninguna página podrá cargar datos hasta que se defina.
    </div>
  );
}
