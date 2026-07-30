import type { ButtonHTMLAttributes, ReactNode } from "react";

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
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  accent?: "primary" | "accent" | "danger" | "success";
  icon?: ReactNode;
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
    <Card className="card-hover p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--muted)]">
          {label}
        </div>
        {icon && (
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-[var(--surface-2)] text-[var(--muted)]">
            {icon}
          </div>
        )}
      </div>
      <div className={`mt-2 text-[1.65rem] font-semibold leading-none tracking-tight tabular ${color}`}>
        {value}
      </div>
      {hint && <div className="mt-1.5 text-xs text-[var(--muted)]">{hint}</div>}
    </Card>
  );
}

export function Badge({
  children,
  tone = "default",
  dot,
}: {
  children: ReactNode;
  tone?: "default" | "success" | "warning" | "danger" | "primary";
  dot?: boolean;
}) {
  const tones: Record<string, string> = {
    default: "bg-[var(--surface-2)] text-[var(--muted)]",
    success: "bg-[var(--success-soft)] text-emerald-700",
    warning: "bg-[var(--warning-soft)] text-amber-700",
    danger: "bg-[var(--danger-soft)] text-red-700",
    primary: "bg-[var(--primary-soft)] text-[var(--primary)]",
  };
  const dots: Record<string, string> = {
    default: "bg-slate-400",
    success: "bg-emerald-500",
    warning: "bg-amber-500",
    danger: "bg-red-500",
    primary: "bg-[var(--primary)]",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${dots[tone]}`} />}
      {children}
    </span>
  );
}

export function SectionTitle({ children, sub }: { children: ReactNode; sub?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-base font-semibold tracking-tight">{children}</h2>
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

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
};

export function Button({ variant = "secondary", className = "", ...props }: ButtonProps) {
  const variants: Record<string, string> = {
    primary:
      "bg-[var(--primary)] text-white shadow-sm hover:bg-[var(--primary-hover)] active:translate-y-px",
    secondary:
      "border border-[var(--border)] bg-[var(--surface)] shadow-sm hover:bg-[var(--surface-2)] active:translate-y-px",
    ghost: "text-[var(--muted)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]",
  };
  return (
    <button
      {...props}
      className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition disabled:pointer-events-none disabled:opacity-50 ${variants[variant]} ${className}`}
    />
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

export function EmptyState({
  icon,
  title,
  hint,
  action,
}: {
  icon?: ReactNode;
  title: string;
  hint?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-[var(--border-strong,var(--border))] px-6 py-12 text-center">
      {icon && (
        <div className="mb-1 flex h-12 w-12 items-center justify-center rounded-full bg-[var(--surface-2)] text-[var(--muted)]">
          {icon}
        </div>
      )}
      <p className="font-medium">{title}</p>
      {hint && <p className="max-w-sm text-sm text-[var(--muted)]">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
