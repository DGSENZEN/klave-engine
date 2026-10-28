"use client";

import { useId, useState, type KeyboardEvent, type ReactNode } from "react";
import { ArrowRight, Check, CircleNotch, Eye, EyeSlash, Warning } from "@phosphor-icons/react";
import { PASSWORD_MIN } from "@/lib/session";
import { buttonClasses, Field, Input } from "@/components/ui";

export { Field };

/** Access forms use the tall control size so inputs and buttons share one edge. */
export const AUTH_INPUT = "h-10 w-full";

/**
 * Password field with a show/hide toggle and a Caps Lock warning. With
 * `rule`, a live line says whether the length the server requires is met,
 * before anyone submits.
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
  const [capsLock, setCapsLock] = useState(false);
  const long = value.length >= PASSWORD_MIN;

  function readCapsLock(event: KeyboardEvent<HTMLInputElement>) {
    setCapsLock(event.getModifierState("CapsLock"));
  }

  return (
    <Field
      label={label}
      htmlFor={inputId}
      aside={aside}
      hint={
        capsLock ? (
          <span className="inline-flex items-center gap-1.5 text-warning">
            <Warning size={12} weight="bold" /> Bloq Mayús está activado
          </span>
        ) : rule ? (
          <span id={ruleId} className={`inline-flex items-center gap-1.5 ${long ? "text-success" : ""}`}>
            {long && <Check size={12} weight="bold" />}
            Al menos {PASSWORD_MIN} caracteres
          </span>
        ) : undefined
      }
    >
      <div className="relative">
        <Input
          id={inputId}
          type={visible ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={readCapsLock}
          onKeyUp={readCapsLock}
          onBlur={() => setCapsLock(false)}
          autoComplete={autoComplete}
          minLength={rule ? PASSWORD_MIN : undefined}
          aria-describedby={rule ? ruleId : undefined}
          autoFocus={autoFocus}
          required
          className={`${AUTH_INPUT} pr-10`}
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

/** The one primary action of an access form; says what it is doing while it works. */
export function SubmitButton({
  busy,
  label,
  busyLabel,
  arrow = true,
}: {
  busy: boolean;
  label: string;
  busyLabel: string;
  arrow?: boolean;
}) {
  return (
    <button
      type="submit"
      className={buttonClasses("primary", "lg", "w-full")}
      disabled={busy}
      aria-busy={busy}
    >
      {busy ? (
        <>
          <CircleNotch size={15} className="animate-spin" /> {busyLabel}
        </>
      ) : (
        <>
          {label} {arrow && <ArrowRight size={15} weight="bold" />}
        </>
      )}
    </button>
  );
}

/** Thin rule with a word in the middle ("o"). */
export function Divider({ children }: { children: ReactNode }) {
  return (
    <div className="my-5 flex items-center gap-3 text-xs text-muted">
      <span className="h-px flex-1 bg-border-strong" />
      {children}
      <span className="h-px flex-1 bg-border-strong" />
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
