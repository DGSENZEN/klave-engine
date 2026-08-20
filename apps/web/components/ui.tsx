import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  TdHTMLAttributes,
  ThHTMLAttributes,
} from "react";
import { Info, Warning, WarningCircle } from "@phosphor-icons/react";

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
        <h1 className="text-[1.4rem] font-semibold leading-tight">{title}</h1>
        {sub && <p className="mt-1 max-w-2xl text-sm text-muted">{sub}</p>}
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
  accent?: "accent" | "danger" | "success" | "primary";
  icon?: ReactNode;
}) {
  const color =
    accent === "accent" || accent === "primary"
      ? "text-accent"
      : accent === "danger"
        ? "text-danger"
        : accent === "success"
          ? "text-success"
          : "text-foreground";
  return (
    <Card className="card-hover p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="microlabel">{label}</div>
        {icon && <div className="text-faint">{icon}</div>}
      </div>
      <div
        className={`mt-2 font-display text-[1.55rem] font-medium leading-none tracking-tight tabular ${color}`}
      >
        {value}
      </div>
      {hint && <div className="mt-1.5 text-xs text-muted">{hint}</div>}
    </Card>
  );
}

export type BadgeTone = "default" | "success" | "warning" | "danger" | "accent";

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
    accent: "bg-accent-soft text-accent",
  };
  const dots: Record<BadgeTone, string> = {
    default: "bg-faint",
    success: "bg-success",
    warning: "bg-warning",
    danger: "bg-danger",
    accent: "bg-accent",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${dots[tone]}`} />}
      {children}
    </span>
  );
}

export function SectionTitle({ children, sub }: { children: ReactNode; sub?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-[0.95rem] font-semibold">{children}</h2>
      {sub && <p className="mt-0.5 text-sm text-muted">{sub}</p>}
    </div>
  );
}

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block animate-spin rounded-full border-2 border-border border-t-foreground ${className}`}
    />
  );
}

/* ---- Buttons: one flat system shared by <Button> and link-buttons. ---- */

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "accent";
export type ButtonSize = "sm" | "md";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-primary text-primary-fg hover:bg-primary-hover",
  secondary:
    "border border-border bg-surface text-foreground hover:border-border-strong hover:bg-surface-2",
  ghost: "text-muted hover:bg-surface-2 hover:text-foreground",
  danger: "bg-danger-soft text-danger hover:opacity-85",
  accent: "bg-accent text-white hover:bg-accent-hover",
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-[13px]",
  md: "h-9 px-3.5 text-sm",
};

/** Shared classes so <Link> can look identical to <Button>. */
export function buttonClasses(
  variant: ButtonVariant = "secondary",
  size: ButtonSize = "md",
  className = "",
): string {
  return `inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-lg font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 ${BUTTON_SIZES[size]} ${BUTTON_VARIANTS[variant]} ${className}`;
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
};

export function Button({
  variant = "secondary",
  size = "md",
  className = "",
  ...props
}: ButtonProps) {
  return <button {...props} className={buttonClasses(variant, size, className)} />;
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
      className={`rounded-md p-1 text-muted transition-colors hover:bg-surface-2 hover:text-foreground disabled:pointer-events-none disabled:opacity-50 ${className}`}
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
      className={`rounded-lg border border-border bg-surface px-3 py-2 text-sm transition-colors placeholder:text-faint focus:border-border-strong focus:outline-none focus:ring-2 focus:ring-ring ${className}`}
    />
  );
}

/* ---- Skeletons: structured shells that mirror the real layout. ---- */

export function Skeleton({
  className = "",
  style,
}: {
  className?: string;
  style?: React.CSSProperties;
}) {
  return <div className={`skeleton ${className}`} style={style} />;
}

/** Title + subtitle placeholder matching PageHeader. */
export function SkeletonHeader() {
  return (
    <div className="mb-6">
      <Skeleton className="h-7 w-64 max-w-full" />
      <Skeleton className="mt-2 h-4 w-96 max-w-full" />
    </div>
  );
}

/** A row of Metric-shaped cards: real card frames, shimmering content. */
export function SkeletonMetrics({ count = 3 }: { count?: number }) {
  return (
    <div
      className={`mb-6 grid gap-4 sm:grid-cols-2 ${
        count >= 4 ? "lg:grid-cols-4" : "lg:grid-cols-3"
      }`}
    >
      {Array.from({ length: count }, (_, i) => (
        <Card key={i} className="p-4">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-3 h-7 w-32" />
          <Skeleton className="mt-2 h-3 w-20" />
        </Card>
      ))}
    </div>
  );
}

/** A table-shaped card: header band plus rows with varied cell widths. */
export function SkeletonTable({ rows = 6 }: { rows?: number }) {
  return (
    <Card className="overflow-hidden">
      <div className="flex gap-4 border-b border-border bg-surface-2 px-4 py-3">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-3 w-40 flex-1" />
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-3 w-24" />
      </div>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 border-b border-border px-4 py-3 last:border-0">
          <Skeleton className="h-3.5 w-14" />
          <Skeleton className={`h-3.5 flex-1 ${i % 3 === 0 ? "max-w-[70%]" : i % 3 === 1 ? "max-w-[55%]" : "max-w-[80%]"}`} />
          <Skeleton className="h-3.5 w-16" />
          <Skeleton className="h-3.5 w-20" />
        </div>
      ))}
    </Card>
  );
}

/** Stacked list-row placeholders inside card frames. */
export function SkeletonCards({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }, (_, i) => (
        <Card key={i} className="p-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-8 w-8 rounded-lg" />
            <div className="flex-1">
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="mt-2 h-3 w-2/3" />
            </div>
            <Skeleton className="h-6 w-20" />
          </div>
        </Card>
      ))}
    </div>
  );
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
      icon: <WarningCircle size={16} weight="bold" className="shrink-0" />,
    },
    warning: {
      box: "bg-warning-soft text-warning",
      icon: <Warning size={16} weight="bold" className="shrink-0" />,
    },
    info: {
      box: "bg-accent-soft text-accent",
      icon: <Info size={16} weight="bold" className="shrink-0" />,
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
  tone = "accent",
  className = "",
}: {
  /** 0..1 */
  value: number;
  tone?: "accent" | "success" | "warning";
  className?: string;
}) {
  const tones: Record<string, string> = {
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
  src,
}: {
  name: string;
  /** Own presence renders in accent; collaborators in ink. */
  self?: boolean;
  size?: "xs" | "sm" | "md";
  title?: string;
  /** Optional photo (e.g. Google account); falls back to initials. */
  src?: string | null;
}) {
  const sizes: Record<string, string> = {
    xs: "h-5 w-5 text-[9px]",
    sm: "h-6 w-6 text-[10px]",
    md: "h-7 w-7 text-[11px]",
  };
  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt={name}
        title={title ?? name}
        referrerPolicy="no-referrer"
        className={`shrink-0 rounded-full border-2 border-surface object-cover ${sizes[size]}`}
      />
    );
  }
  return (
    <span
      title={title ?? name}
      className={`flex shrink-0 items-center justify-center rounded-full border-2 border-surface font-semibold ${sizes[size]} ${
        self ? "bg-accent text-white" : "bg-primary text-primary-fg"
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
      className={`microlabel px-4 py-3 font-medium ${alignCls} ${className}`}
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
