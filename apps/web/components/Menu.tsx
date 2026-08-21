"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { CaretDown, DotsThreeVertical } from "@phosphor-icons/react";
import { buttonClasses } from "@/components/ui";

/** Minimal kebab menu: closes on outside click and Escape. */
export function KebabMenu({
  label,
  children,
}: {
  label: string;
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((current) => !current);
        }}
        className="rounded-md p-1.5 text-faint transition-colors hover:bg-surface-2 hover:text-foreground"
      >
        <DotsThreeVertical size={18} weight="bold" />
      </button>
      {open && (
        <div className="toast-in absolute right-0 top-full z-40 mt-1 w-52 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg">
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

/** Labeled dropdown sharing the kebab's outside-click/Escape behavior. */
export function ButtonMenu({
  label,
  icon,
  children,
}: {
  label: string;
  icon?: ReactNode;
  children: (close: () => void) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: PointerEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) setOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((current) => !current)}
        className={buttonClasses("secondary")}
      >
        {icon}
        {label}
        <CaretDown size={13} weight="bold" className={open ? "rotate-180" : ""} />
      </button>
      {open && (
        <div className="toast-in absolute right-0 top-full z-40 mt-1 w-60 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg">
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

export function MenuItem({
  onSelect,
  danger,
  children,
}: {
  onSelect: () => void;
  danger?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onSelect();
      }}
      className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors ${
        danger ? "text-danger hover:bg-danger-soft" : "hover:bg-surface-2"
      }`}
    >
      {children}
    </button>
  );
}
