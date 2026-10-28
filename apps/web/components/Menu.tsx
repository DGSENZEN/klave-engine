"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { CaretDown, DotsThreeVertical } from "@phosphor-icons/react";
import { buttonClasses, iconButtonClasses } from "@/components/ui";

/** Minimal kebab menu: closes on outside click and Escape. */
export function KebabMenu({
  label,
  icon,
  children,
}: {
  label: string;
  /** Trigger icon; defaults to the vertical dots. */
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
        aria-label={label}
        aria-expanded={open}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((current) => !current);
        }}
        data-tip={label}
        className={iconButtonClasses("sm", "text-faint")}
      >
        {icon ?? <DotsThreeVertical />}
      </button>
      {open && (
        <div className="menu-pop absolute right-0 top-full z-40 mt-1 w-52 origin-top-right overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg">
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
  width = "w-60",
  children,
}: {
  label: string;
  icon?: ReactNode;
  /** Tailwind width of the dropdown; wider menus can carry a hint per item. */
  width?: string;
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
        <CaretDown size={12} className={`transition-transform duration-150 ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div
          ref={keepOnScreen}
          className={`menu-pop absolute right-0 top-full z-40 mt-1 origin-top-right ${width} max-w-[calc(100vw-2rem)] overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-lg`}
        >
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

/** The menu hangs from the trigger's right edge; when the page header wraps
 *  and the trigger lands on the left, that pushes it off-screen (the Importar…
 *  options were cut in half), so it hangs from the left edge instead. */
function keepOnScreen(menu: HTMLDivElement | null) {
  if (!menu) return;
  if (menu.getBoundingClientRect().left < 8) {
    menu.style.right = "auto";
    menu.style.left = "0";
  }
}

export function MenuItem({
  onSelect,
  danger,
  hint,
  children,
}: {
  onSelect: () => void;
  danger?: boolean;
  /** One line under the label: what the action expects or does. */
  hint?: ReactNode;
  children: ReactNode;
}) {
  if (hint) {
    return (
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onSelect();
        }}
        className={`flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left text-sm transition-colors ${
          danger ? "text-danger hover:bg-danger-soft" : "hover:bg-surface-2"
        }`}
      >
        <span className="flex items-center gap-2">{children}</span>
        <span className="text-xs font-normal text-muted">{hint}</span>
      </button>
    );
  }
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
