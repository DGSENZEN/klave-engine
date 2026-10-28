import type React from "react";
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TdHTMLAttributes,
  ThHTMLAttributes,
} from "react";
import { CaretDown, Info, Warning, WarningCircle } from "@phosphor-icons/react";

export function Card({
  children,
  className = "",
  tour,
}: {
  children: ReactNode;
  className?: string;
  /** Ancla del recorrido guiado (data-tour). */
  tour?: string;
}) {
  return (
    <div className={`card ${className}`} data-tour={tour}>
      {children}
    </div>
  );
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
    <div className="mb-5 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        <h1 className="text-[1.25rem] font-semibold leading-tight">{title}</h1>
        {sub && <p className="mt-1 max-w-3xl text-[13px] text-muted">{sub}</p>}
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
    <Card className="px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs text-muted">{label}</div>
        {icon && <div className="text-faint">{icon}</div>}
      </div>
      <div
        className={`mt-1.5 font-display text-[1.375rem] font-medium leading-none tracking-tight tabular ${color}`}
      >
        {value}
      </div>
      {hint && <div className="mt-1.5 text-xs text-muted">{hint}</div>}
    </Card>
  );
}

export type Stat = {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "accent" | "danger" | "success" | "warning";
  /** A stat that filters: clicking it shows exactly the rows it counts. */
  onClick?: () => void;
  active?: boolean;
};

/**
 * A row of figures read as one instrument, not a row of cards: hairline
 * dividers, one baseline. On phones it folds into two columns; the -1px
 * offsets tuck each cell's top/left rule under the frame so only inner
 * dividers show at any column count.
 */
export function StatStrip({
  stats,
  className = "",
  tour,
}: {
  stats: Stat[];
  className?: string;
  tour?: string;
}) {
  const tones = {
    accent: "text-accent",
    danger: "text-danger",
    success: "text-success",
    warning: "text-warning",
  } as const;
  return (
    <div
      data-tour={tour}
      className={`grid grid-cols-2 overflow-clip rounded-[10px] border border-border bg-surface max-sm:[&>*:last-child:nth-child(odd)]:col-span-2 sm:auto-cols-fr sm:grid-flow-col sm:grid-cols-none ${className}`}
    >
      {stats.map((stat) => {
        const body = (
          <>
            <span className="block text-xs text-muted">{stat.label}</span>
            <span
              className={`mt-1 block font-display text-[1.25rem] font-medium leading-tight tracking-tight tabular ${
                stat.tone ? tones[stat.tone] : "text-foreground"
              }`}
            >
              {stat.value}
            </span>
            {stat.hint && <span className="mt-0.5 block text-xs text-muted">{stat.hint}</span>}
          </>
        );
        const cell = "relative -ml-px -mt-px min-w-0 border-l border-t border-border px-4 py-2.5 text-left";
        return stat.onClick ? (
          <button
            key={stat.label}
            type="button"
            onClick={stat.onClick}
            aria-pressed={!!stat.active}
            className={`${cell} transition-colors hover:bg-surface-2/70 ${
              stat.active ? "bg-accent-soft/40" : ""
            }`}
          >
            {body}
            {stat.active && (
              <span className="absolute inset-x-0 bottom-0 h-0.5 bg-accent" aria-hidden />
            )}
          </button>
        ) : (
          <div key={stat.label} className={cell}>
            {body}
          </div>
        );
      })}
    </div>
  );
}

export type BadgeTone = "default" | "success" | "warning" | "danger" | "accent";

export function Badge({
  children,
  tone = "default",
  dot,
  title,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  dot?: boolean;
  title?: string;
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
      title={title}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded px-1.5 text-xs font-medium leading-5 ${tones[tone]}`}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${dots[tone]}`} />}
      {children}
    </span>
  );
}

export function SectionTitle({ children, sub }: { children: ReactNode; sub?: string }) {
  return (
    <div className="mb-3">
      <h2 className="text-[0.9375rem] font-semibold">{children}</h2>
      {sub && <p className="mt-0.5 text-[13px] text-muted">{sub}</p>}
    </div>
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
  accent: "bg-accent text-accent-fg hover:bg-accent-hover",
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "h-7 gap-1.5 px-2.5 text-[13px]",
  md: "h-8 px-3 text-[13px]",
};

/** Shared classes so <Link> can look identical to <Button>. */
export function buttonClasses(
  variant: ButtonVariant = "secondary",
  size: ButtonSize = "md",
  className = "",
): string {
  return `inline-flex select-none items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 ${BUTTON_SIZES[size]} ${BUTTON_VARIANTS[variant]} ${className}`;
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
}: React.ComponentProps<"input">) {
  return (
    <input
      {...props}
      className={`rounded-md border border-border bg-surface px-2.5 py-[5px] text-data transition-colors placeholder:text-faint focus:border-border-strong focus:outline-none focus:ring-2 focus:ring-ring ${className}`}
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
    <div className="mb-5 grid grid-cols-2 overflow-clip rounded-[10px] border border-border bg-surface sm:auto-cols-fr sm:grid-flow-col sm:grid-cols-none">
      {Array.from({ length: count }, (_, i) => (
        <div key={i} className="-ml-px -mt-px border-l border-t border-border px-4 py-2.5">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="mt-2 h-5 w-28" />
        </div>
      ))}
    </div>
  );
}

/** A table-shaped card: header band plus rows with varied cell widths. */
export function SkeletonTable({ rows = 6 }: { rows?: number }) {
  return (
    <Card className="overflow-hidden">
      <div className="flex gap-4 border-b border-border bg-surface-2 px-3 py-3">
        <Skeleton className="h-3 w-16" />
        <Skeleton className="h-3 w-40 flex-1" />
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-3 w-24" />
      </div>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 border-b border-border px-3 py-2.5 last:border-0">
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
    <div className="flex flex-col items-center justify-center gap-2 rounded-[10px] border border-dashed border-border-strong px-6 py-10 text-center">
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
      role={tone === "danger" ? "alert" : "status"}
      className={`flex flex-wrap items-center justify-between gap-x-3 gap-y-2 rounded-md px-3.5 py-2.5 text-[13px] ${tones[tone].box}`}
    >
      <div className="flex min-w-0 flex-1 basis-64 items-center gap-2">
        {tones[tone].icon}
        <span className="min-w-0">{children}</span>
      </div>
      {action && <div className="shrink-0">{action}</div>}
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
        self ? "bg-accent text-accent-fg" : "bg-primary text-primary-fg"
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
  tour,
  sticky,
}: {
  children: ReactNode;
  className?: string;
  tour?: string;
  /** Long tables: the header stays under the shell while you scroll (lg+). */
  sticky?: boolean;
}) {
  return (
    <Card className={`overflow-clip ${className}`} tour={tour}>
      <div className="table-scroll" data-sticky={sticky ? "" : undefined}>
        <table className="w-full text-data">{children}</table>
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
      className={`microlabel h-9 px-3 font-medium ${alignCls} ${className}`}
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
  return <td {...props} className={`px-3 py-1.5 ${alignCls} ${className}`} />;
}

/* ---- Form controls that match <Input>: one look for every select and checkbox. ---- */

export function Select({
  className = "",
  size = "md",
  ...props
}: Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> & { size?: "sm" | "md" }) {
  const pad = size === "sm" ? "px-2 py-1 text-xs" : "px-2 py-[5px] text-data";
  return (
    <select
      className={`max-w-full rounded-md border border-border bg-surface text-foreground outline-none transition focus:border-border-strong focus:ring-2 focus:ring-accent/20 disabled:opacity-60 ${pad} ${className}`}
      {...props}
    />
  );
}

export function Checkbox({
  label,
  className = "",
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & { label?: ReactNode }) {
  const box = (
    <input
      type="checkbox"
      className={`h-4 w-4 shrink-0 rounded border-border accent-accent ${label ? "" : className}`}
      {...props}
    />
  );
  if (!label) return box;
  return (
    <label className={`inline-flex cursor-pointer items-center gap-2 text-sm ${className}`}>
      {box}
      <span className="min-w-0">{label}</span>
    </label>
  );
}

/**
 * One rule for "how sure is the engine": ≥ 0.7 reads as firm, ≥ 0.45 as a
 * doubt to check, below that as weak. The same thresholds drive the money
 * gate and the revisión, so the colour means the same thing everywhere.
 */
export const CONFIDENCE_FIRM = 0.7;
export const CONFIDENCE_DOUBT = 0.45;

export function confidenceTone(value: number): BadgeTone {
  return value >= CONFIDENCE_FIRM ? "success" : value >= CONFIDENCE_DOUBT ? "warning" : "danger";
}

export function ConfidenceBadge({ value, dot = true }: { value: number; dot?: boolean }) {
  const tone = confidenceTone(value);
  // A firm read is the expected case: it stays quiet so the doubts stand out
  // down a column of hundreds. Only dudosa/débil get a fill.
  if (tone === "success") {
    return (
      <span className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs leading-5 text-muted">
        {dot && <span className="h-1.5 w-1.5 rounded-full bg-success" />}
        {Math.round(value * 100)}%
      </span>
    );
  }
  return (
    <Badge dot={dot} tone={tone}>
      {Math.round(value * 100)}%
    </Badge>
  );
}

/** A section that opens and closes, with the summary line always visible. */
export function Disclosure({
  open,
  onToggle,
  icon,
  title,
  summary,
  children,
  className = "",
}: {
  open: boolean;
  onToggle: () => void;
  icon?: ReactNode;
  title: ReactNode;
  summary?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Card className={`overflow-hidden ${className}`}>
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        {icon && (
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-surface-2 text-foreground">
            {icon}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium">{title}</div>
          {summary && <div className="text-xs text-muted">{summary}</div>}
        </div>
        <CaretDown
          size={14}
          className={`shrink-0 text-muted transition ${open ? "rotate-180" : ""}`}
        />
      </button>
      {open && <div className="border-t border-border px-4 py-3">{children}</div>}
    </Card>
  );
}

/** Horizontal tabs for one page with several working areas. */
export function Tabs<K extends string>({
  value,
  onChange,
  items,
  className = "",
}: {
  value: K;
  onChange: (key: K) => void;
  items: { key: K; label: ReactNode; count?: number }[];
  className?: string;
}) {
  return (
    <div role="tablist" className={`tablist flex gap-1 overflow-x-auto ${className}`}>
      {items.map((item) => {
        const active = item.key === value;
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.key)}
            className={`inline-flex shrink-0 items-center gap-1.5 border-b-2 px-2.5 py-2 text-[13px] transition-colors ${
              active
                ? "border-foreground font-medium text-foreground"
                : "border-transparent text-muted hover:text-foreground"
            }`}
          >
            {item.label}
            {item.count != null && (
              <span className="tabular rounded-full bg-surface-2 px-1.5 text-[11px] text-muted">
                {item.count.toLocaleString("es-MX")}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
