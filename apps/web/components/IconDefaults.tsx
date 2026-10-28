"use client";

import type { ReactNode } from "react";
import { IconContext } from "@phosphor-icons/react";

/**
 * One icon voice for the whole app: 16 px, bold (a 1.5 px stroke — the same
 * weight as Geist's medium stems at 13–14 px). A call site names a size only
 * when it is not chrome: 14 inside dense text, 20 for a node glyph or an
 * empty state. Duotone is kept for the six process nodes; fill only for
 * state (a closed lock, a solid check).
 */
export function IconDefaults({ children }: { children: ReactNode }) {
  return (
    <IconContext.Provider value={{ size: 16, weight: "bold", mirrored: false }}>
      {children}
    </IconContext.Provider>
  );
}
