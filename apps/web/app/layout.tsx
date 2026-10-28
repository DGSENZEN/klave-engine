import type { Metadata, Viewport } from "next";
import { ApiBaseWarning } from "@/components/ApiBaseWarning";
import { CopilotFab } from "@/components/CopilotFab";
import { IconDefaults } from "@/components/IconDefaults";
import { RecorridoProvider } from "@/components/recorrido/RecorridoProvider";
import { SessionRecovery } from "@/components/SessionRecovery";
import localFont from "next/font/local";
import { THEME_INIT_SCRIPT } from "@/lib/theme";
import "./globals.css";

const geistSans = localFont({
  src: "./fonts/Geist.woff2",
  variable: "--font-geist-sans",
  weight: "100 900",
  display: "swap",
});
const geistMono = localFont({
  src: "./fonts/GeistMono.woff2",
  variable: "--font-geist-mono",
  weight: "100 900",
  display: "swap",
});
const spaceGrotesk = localFont({
  src: "./fonts/SpaceGrotesk.woff2",
  variable: "--font-space-grotesk",
  weight: "500 700",
  display: "swap",
});

export const metadata: Metadata = {
  // Cada ruta pone su nombre («Presupuesto · Klave»); la portada se queda con el completo.
  title: { template: "%s · Klave", default: "Klave — Ingeniería de Costos" },
  description:
    "Lee planos estructurales (DWG/DXF) y genera presupuesto, programa de obra y flujo financiero con evidencia inspeccionable.",
  applicationName: "Klave",
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f7f7f8" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0b" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="es"
      className={`${geistSans.variable} ${geistMono.variable} ${spaceGrotesk.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-full">
        <IconDefaults>
          <ApiBaseWarning />
          <SessionRecovery />
          {children}
          {/* Siempre a la mano, en cualquier pantalla de trabajo. */}
          <CopilotFab />
          {/* El recorrido guiado: encima de todo, nunca bloquea el trabajo. */}
          <RecorridoProvider />
        </IconDefaults>
      </body>
    </html>
  );
}
