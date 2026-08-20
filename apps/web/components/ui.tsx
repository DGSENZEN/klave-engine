import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  TdHTMLAttributes,
  ThHTMLAttributes,
} from "react";
import { CircleAlert, Info, TriangleAlert } from "lucide-react";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`card ${className}`}>{children}</div>;
}

export function PageHeader({
  title,
  sub,
  actions,
}: {
  title: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {sub && <p className="mt-1 text-sm text-muted">{sub}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
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
      ? "text-primary"
      : accent === "accent"
        ? "text-accent"
        : accent === "danger"
          ? "text-danger"
          : accent === "success"
            ? "text-success"
            : "text-foreground";
  return (
    <Card className="card-hover p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
          {label}
        </div>
        {icon && (
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-surface-2 text-muted">
            {icon}
          </div>
        )}
      </div>
      <div className={`mt-2 text-[1.65rem] font-semibold leading-none tracking-tight tabular ${color}`}>
        {value}
      </div>
      {hint && <div className="mt-1.5 text-xs text-muted">{hint}</div>}
    </Card>
  );
}

export type BadgeTone = "default" | "success" | "warning" | "danger" | "primary";

export function Badge({
  children,
  tone = "default",
  dot,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  dot?: boolean;
}) {
  const tones: Record<BadgeTone, string> = {
    default: "bg-surface-2 text-muted",
    success: "bg-success-soft text-success",
    warning: "bg-warning-soft text-warning",
    danger: "bg-danger-soft text-danger",
    primary: "bg-primary-soft text-primary",
  };
  const dots: Record<BadgeTone, string> = {
    default: "bg-faint",
    success: "bg-success",
    warning: "bg-warning",
    danger: "bg-danger",
    primary: "bg-primary",
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
      {sub && <p className="mt-0.5 text-sm text-muted">{sub}</p>}
    </div>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block animate-spin rounded-full border-2 border-border border-t-primary ${className}`}
    />
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
};

export function Button({
  variant = "secondary",
  size = "md",
  className = "",
  ...props
}: ButtonProps) {
  const variants: Record<string, string> = {
    primary:
      "bg-primary text-primary-fg shadow-sm hover:bg-primary-hover active:translate-y-px",
    secondary:
      "border border-border bg-surface shadow-sm hover:bg-surface-2 active:translate-y-px",
    ghost: "text-muted hover:bg-surface-2 hover:text-foreground",
    danger: "bg-danger-soft text-danger hover:opacity-90 active:translate-y-px",
  };
  const sizes: Record<string, string> = {
    sm: "px-2.5 py-1.5 text-xs",
    md: "px-3 py-2 text-sm",
  };
  return (
    <button
      {...props}
      className={`inline-flex items-center gap-2 rounded-lg font-medium transition disabled:pointer-events-none disabled:opacity-50 ${sizes[size]} ${variants[variant]} ${className}`}
    />
  );
}

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  "aria-label": string;
};

/** Icon-only action; aria-label is required by the type. */
export function IconButton({ className = "", ...props }: IconButtonProps) {
  return (
    <button
      type="button"
      {...props}
      className={`rounded-md p-1 text-muted transition hover:bg-surface-2 hover:text-foreground disabled:pointer-events-none disabled:opacity-50 ${className}`}
    />
  );
}

export function Input({
  className = "",
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`rounded-lg border border-border bg-surface px-3 py-2 text-sm shadow-xs transition placeholder:text-faint focus:border-primary focus:outline-none focus:ring-2 focus:ring-ring ${className}`}
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
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border-strong px-6 py-12 text-center">
      {icon && (
        <div className="mb-1 flex h-12 w-12 items-center justify-center rounded-full bg-surface-2 text-muted">
          {icon}
        </div>
      )}
      <p className="font-medium">{title}</p>
      {hint && <p className="max-w-sm text-sm text-muted">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function Callout({
  tone,
  children,
  action,
}: {
  tone: "danger" | "warning" | "info";
  children: ReactNode;
  action?: ReactNode;
}) {
  const tones: Record<string, { box: string; icon: ReactNode }> = {
    danger: {
      box: "bg-danger-soft text-danger",
      icon: <CircleAlert size={16} className="shrink-0" />,
    },
    warning: {
      box: "bg-warning-soft text-warning",
      icon: <TriangleAlert size={16} className="shrink-0" />,
    },
    info: {
      box: "bg-primary-soft text-primary",
      icon: <Info size={16} className="shrink-0" />,
    },
  };
  return (
    <div
      className={`flex items-center justify-between gap-3 rounded-lg px-4 py-3 text-sm ${tones[tone].box}`}
    >
      <div className="flex min-w-0 items-center gap-2">
        {tones[tone].icon}
        <span className="min-w-0">{children}</span>
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

export function ProgressBar({
  value,
  tone = "primary",
  className = "",
}: {
  /** 0..1 */
  value: number;
  tone?: "primary" | "accent" | "success" | "warning";
  className?: string;
}) {
  const tones: Record<string, string> = {
    primary: "bg-primary",
    accent: "bg-accent",
    success: "bg-success",
    warning: "bg-warning",
  };
  const pct = Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className={`h-2 overflow-hidden rounded-full bg-surface-2 ${className}`}>
      <div
        className={`h-full rounded-full transition-[width] duration-500 ${tones[tone]}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function Avatar({
  name,
  self,
  size = "md",
  title,
}: {
  name: string;
  /** Own presence renders in primary; collaborators in accent. */
  self?: boolean;
  size?: "xs" | "sm" | "md";
  title?: string;
}) {
  const sizes: Record<string, string> = {
    xs: "h-5 w-5 text-[9px]",
    sm: "h-6 w-6 text-[10px]",
    md: "h-7 w-7 text-[11px]",
  };
  return (
    <span
      title={title ?? name}
      className={`flex shrink-0 items-center justify-center rounded-full border-2 border-surface font-semibold text-primary-fg ${sizes[size]} ${
        self ? "bg-primary" : "bg-accent"
      }`}
    >
      {initials(name)}
    </span>
  );
}

/* ---- Table primitives: consistent paddings, header treatment, scroll. ---- */

export function TableCard({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={`overflow-hidden ${className}`}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">{children}</table>
      </div>
    </Card>
  );
}

export function Th({
  className = "",
  align = "left",
  ...props
}: ThHTMLAttributes<HTMLTableCellElement> & { align?: "left" | "right" | "center" }) {
  const alignCls =
    align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
  return (
    <th
      {...props}
      className={`px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted ${alignCls} ${className}`}
    />
  );
}

export function Td({
  className = "",
  align = "left",
  ...props
}: TdHTMLAttributes<HTMLTableCellElement> & { align?: "left" | "right" | "center" }) {
  const alignCls =
    align === "right" ? "text-right" : align === "center" ? "text-center" : "text-left";
  return <td {...props} className={`px-4 py-3 ${alignCls} ${className}`} />;
}
