"use client";

import type { ReactNode } from "react";
import { GateGuard } from "@/components/GateGuard";

export default function Layout({ children }: { children: ReactNode }) {
  return <GateGuard node="programa">{children}</GateGuard>;
}
