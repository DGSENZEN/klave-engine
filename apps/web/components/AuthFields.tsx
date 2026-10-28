"use client";

import { useId, useState, type ReactNode } from "react";
import { Check, Eye, EyeSlash } from "@phosphor-icons/react";
import { PASSWORD_MIN } from "@/lib/session";
import { Input } from "@/components/ui";

/** Label above, control, optional hint below. Labels stay visible while typing. */
export function Field({
  label,
  htmlFor,
  aside,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  aside?: ReactNode;
  hint?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <label htmlFor={htmlFor} className="text-sm font-medium">
          {label}
        </label>
        {aside}
      </div>
      {children}
      {hint && <div className="mt-1.5 text-xs text-muted">{hint}</div>}
    </div>
  );
}

/**
 * Password field with a show/hide toggle. With `rule`, a live line says
 * whether the length the server requires is met, before anyone submits.
 */
export function PasswordField({
  label,
  value,
  onChange,
  autoComplete,
  rule = false,
  aside,
  autoFocus,
  id,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  autoComplete: "current-password" | "new-password";
  rule?: boolean;
  aside?: ReactNode;
  autoFocus?: boolean;
  id?: string;
}) {
  const generated = useId();
  const inputId = id ?? generated;
  const ruleId = `${inputId}-regla`;
  const [visible, setVisible] = useState(false);
  const long = value.length >= PASSWORD_MIN;

  return (
    <Field
      label={label}
      htmlFor={inputId}
      aside={aside}
      hint={
        rule && (
          <span id={ruleId} className={`inline-flex items-center gap-1.5 ${long ? "text-success" : ""}`}>
            {long && <Check size={12} weight="bold" />}
            Al menos {PASSWORD_MIN} caracteres
          </span>
        )
      }
    >
      <div className="relative">
        <Input
          id={inputId}
          type={visible ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          minLength={rule ? PASSWORD_MIN : undefined}
          aria-describedby={rule ? ruleId : undefined}
          autoFocus={autoFocus}
          required
          className="w-full pr-10"
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Ocultar contraseña" : "Mostrar contraseña"}
          aria-pressed={visible}
          className="absolute inset-y-0 right-0 flex w-10 items-center justify-center rounded-r-lg text-muted transition-colors hover:text-foreground"
        >
          {visible ? <EyeSlash size={16} /> : <Eye size={16} />}
        </button>
      </div>
    </Field>
  );
}

/** Thin rule with a word in the middle ("o con tu correo"). */
export function Divider({ children }: { children: ReactNode }) {
  return (
    <div className="my-5 flex items-center gap-3 text-xs text-faint">
      <span className="h-px flex-1 bg-border" />
      {children}
      <span className="h-px flex-1 bg-border" />
    </div>
  );
}

/** Remembers the email typed on one auth screen so the next one starts filled. */
const EMAIL_KEY = "klave.auth.email";

export function rememberAuthEmail(email: string): void {
  try {
    window.sessionStorage.setItem(EMAIL_KEY, email.trim());
  } catch {}
}

export function recallAuthEmail(): string {
  try {
    return window.sessionStorage.getItem(EMAIL_KEY) ?? "";
  } catch {
    return "";
  }
}
