import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = { title: "Lectura del plano" };

export default function Layout({ children }: { children: ReactNode }) {
  return children;
}
