import type { Metadata } from "next";
import type { ReactNode } from "react";

// Un título de texto aquí cortaría la plantilla de la raíz para todo lo de
// abajo («Revisión» en vez de «Revisión · Klave»): se repite la plantilla.
export const metadata: Metadata = {
  title: { template: "%s · Klave", default: "Obra" },
};

export default function Layout({ children }: { children: ReactNode }) {
  return children;
}
