"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import {
  LayoutDashboard,
  Map,
  Receipt,
  Calculator,
  Coins,
  CalendarDays,
  LineChart,
  TriangleAlert,
  ChevronLeft,
  Building2,
} from "lucide-react";

type Item = { key: string; label: string; icon: ReactNode; href: string; soon?: boolean };

function nav(id: string): { group: string; items: Item[] }[] {
  const b = `/proyecto/${id}`;
  return [
    {
      group: "Proyecto",
      items: [
        { key: "resumen", label: "Resumen", icon: <LayoutDashboard size={18} />, href: b },
        { key: "plano", label: "Visor del Plano", icon: <Map size={18} />, href: `${b}/plano` },
      ],
    },
    {
      group: "Ingeniería de Costos",
      items: [
        {
          key: "presupuesto",
          label: "Presupuesto",
          icon: <Receipt size={18} />,
          href: `${b}/presupuesto`,
        },
        {
          key: "parametros",
          label: "Parámetros e Insumos",
          icon: <Coins size={18} />,
          href: `${b}/parametros`,
        },
        {
          key: "apu",
          label: "Precios Unitarios",
          icon: <Calculator size={18} />,
          href: `${b}/presupuesto`,
          soon: true,
        },
      ],
    },
    {
      group: "Planeación y Finanzas",
      items: [
        {
          key: "programa",
          label: "Programa de Obra",
          icon: <CalendarDays size={18} />,
          href: `${b}/presupuesto`,
          soon: true,
        },
        {
          key: "finanzas",
          label: "Flujo Financiero",
          icon: <LineChart size={18} />,
          href: `${b}/presupuesto`,
          soon: true,
        },
        {
          key: "riesgos",
          label: "Riesgos",
          icon: <TriangleAlert size={18} />,
          href: `${b}/presupuesto`,
          soon: true,
        },
      ],
    },
  ];
}

export function ProjectShell({
  id,
  name,
  children,
}: {
  id: string;
  name?: string;
  children: ReactNode;
}) {
  const pathname = usePathname();
  const groups = nav(id);
  return (
    <div className="flex min-h-screen">
      <aside className="flex w-64 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)]">
        <Link
          href="/"
          className="flex items-center gap-2 px-5 py-4 text-sm text-[var(--muted)] hover:text-[var(--foreground)]"
        >
          <ChevronLeft size={16} /> Proyectos
        </Link>
        <div className="flex items-center gap-2 px-5 pb-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--primary)] text-white">
            <Building2 size={18} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold" title={name}>
              {name ?? id}
            </div>
            <div className="text-xs text-[var(--muted)]">Ingeniería de costos</div>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto px-3 pb-6">
          {groups.map((g) => (
            <div key={g.group} className="mb-4">
              <div className="px-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-[var(--muted)]">
                {g.group}
              </div>
              {g.items.map((it) => {
                const active = it.href === pathname && !it.soon;
                return (
                  <Link
                    key={it.key}
                    href={it.soon ? pathname : it.href}
                    aria-disabled={it.soon}
                    className={`mb-0.5 flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition ${
                      active
                        ? "bg-blue-50 font-medium text-[var(--primary)]"
                        : it.soon
                          ? "cursor-default text-slate-300"
                          : "text-slate-600 hover:bg-[var(--surface-2)]"
                    }`}
                  >
                    {it.icon}
                    <span className="flex-1">{it.label}</span>
                    {it.soon && (
                      <span className="rounded bg-[var(--surface-2)] px-1.5 py-0.5 text-[10px] text-[var(--muted)]">
                        pronto
                      </span>
                    )}
                  </Link>
                );
              })}
            </div>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 overflow-x-hidden">{children}</main>
    </div>
  );
}
