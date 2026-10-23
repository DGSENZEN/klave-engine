import type { Metadata } from "next";
import type { ReactNode } from "react";
import { GateGuard } from "@/components/GateGuard";

export const metadata: Metadata = { title: "Finiquito" };

export default function Layout({ children }: { children: ReactNode }) {
  return <GateGuard node="contrato">{children}</GateGuard>;
}
