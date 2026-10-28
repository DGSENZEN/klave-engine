import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Parámetros e insumos" };

// Sin candado: los parámetros alimentan al presupuesto (que tampoco espera
// candado) y el paso 3 de la ruta de verificación enlaza aquí. Esperar al
// programa los dejaba fuera de alcance justo cuando hay que revisarlos.
export default function Layout({ children }: { children: ReactNode }) {
  return children;
}
