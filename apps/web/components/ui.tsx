import type { ReactNode } from "react";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`card ${className}`}>{children}</div>;
}

export function Metric({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  accent?: "primary" | "accent" | "danger" | "success";
}) {
  const color =
    accent === "primary"
      ? "text-[var(--primary)]"
      : accent === "accent"
        ? "text-[var(--accent)]"
        : accent === "danger"
          ? "text-[var(--danger)]"
          : accent === "success"
            ? "text-[var(--success)]"
            : "text-[var(--foreground)]";
  return (
    <Card className="p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-[var(--muted)]">
        {label}
      </div>
      <div className={`mt-1.5 text-2xl font-semibold tabular ${color}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-[var(--muted)]">{hint}</div>}
    </Card>
  );
}

export function Badge({
  children,
  tone = "default",
}: {
  children: ReactNode;
  tone?: "default" | "success" | "warning" | "danger" | "primary";
}) {
  const tones: Record<string, string> = {
    default: "bg-[var(--surface-2)] text-[var(--muted)]",
    success: "bg-emerald-50 text-emerald-700",
    warning: "bg-amber-50 text-amber-700",
    danger: "bg-red-50 text-red-700",
    primary: "bg-blue-50 text-blue-700",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

export function SectionTitle({ children, sub }: { children: ReactNode; sub?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-lg font-semibold">{children}</h2>
      {sub && <p className="mt-0.5 text-sm text-[var(--muted)]">{sub}</p>}
    </div>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block animate-spin rounded-full border-2 border-[var(--border)] border-t-[var(--primary)] ${className}`}
    />
  );
}
