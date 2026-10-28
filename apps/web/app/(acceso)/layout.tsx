import type { ReactNode } from "react";
import Link from "next/link";
import { Buildings } from "@phosphor-icons/react/dist/ssr";
import { AsciiPond } from "@/components/AsciiPond";
import { ThemeToggle } from "@/components/ThemeToggle";

/**
 * The one frame for every access screen (bienvenida, registro, recuperar,
 * restablecer, invitación, verificar). It lives in a layout so moving between
 * them keeps the same pond swimming instead of starting a new one. Wide
 * screens split in two; narrow screens keep only the task.
 */
export default function AccesoLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen">
      <aside className="relative hidden w-[55%] overflow-hidden border-r border-border bg-background lg:flex lg:flex-col">
        <AsciiPond className="absolute inset-0" />
        <div className="relative flex flex-1 flex-col justify-between p-10 xl:p-14">
          <Brand />
          <p
            data-pond-avoid
            className="max-w-md font-display text-3xl font-semibold leading-tight tracking-tight xl:text-4xl"
          >
            Ingeniería de costos a partir de planos estructurales.
          </p>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col bg-surface px-5 py-5 sm:px-10">
        <div className="flex items-center justify-between gap-4">
          <div className="lg:invisible">
            <Brand />
          </div>
          <ThemeToggle />
        </div>
        <div className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center py-12">
          {children}
        </div>
      </main>
    </div>
  );
}

function Brand() {
  return (
    <Link href="/bienvenida" data-pond-avoid className="inline-flex items-center gap-2.5">
      <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-fg">
        <Buildings size={17} weight="duotone" />
      </span>
      <span className="font-display text-lg font-semibold tracking-tight">Klave</span>
    </Link>
  );
}
