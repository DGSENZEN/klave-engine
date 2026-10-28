---
version: 1
slug: "apps-web-app-portada-page-tsx"
primary_target: "apps/web/app/portada/page.tsx"
related_targets: []
---

# Portada pública (landing)

Scope: public landing for signed-out visitors at `/portada`. Mode: Persuade. Audience: cost engineers and office admins at Mexican construction offices. Action: Crear cuenta (`/registro`, admin approval) with Entrar (`/bienvenida`) secondary. Proof: only what the product truly does (PRODUCT.md); demonstration rows are synthetic and labelled. No customers, metrics, prices or time-saved claims. New visual world for marketing only; the app keeps its ink + cobalt system.

## Direction contract

THESIS: The bid is one line with stations: Planos → Revisión → Catálogo → Generadores → OPUS · Neodata. The strokes that draw the plan become the rows of numbers. Refuses the split hero with screenshot and feature-card row.

OWN-WORLD: Cool white ground, ink black, one rosa mexicano line (#e4007c family) reserved for the live path and the primary action. Mexico 68 parallel offset strokes (bundles of equal-weight lines, rounded line bends like a metro diagram), white station rings with ink stroke, two-digit station numbers. Grotesk display set tight and large, tabular mono for measures. No cards, no icon tiles, no gradients, no shadows.

STORY: The visitor sees in one viewport that Klave turns a DWG into generadores with evidence, follows the line down through the stations (each with its lock and what is known/unknown), sees a synthetic generador row tied to its eje and hoja, learns what Klave refuses to invent, and creates an account.

FIRST VIEWPORT: Nav (wordmark left, Cómo funciona / Entrar right). Headline ~7vw across 2/3 width top-left, one-line subcopy, Crear cuenta (rosa pill) + Entrar. Below, a bundle of four parallel lines runs full width and bends up the right edge; five numbered stations sit on it, labelled under.

FORM: Línea 68, position 6 of 7 on the grounded list, assigned by the roll. seed:01e2aff59e5f1212. Signature interaction: the line draws itself on load; hovering or keying 1–5 lights a station and scrolls to its section; scrolling advances a rosa marker along the line.

ADAPTATIONS (recorded after build): stations are Planos → Lectura → Revisión → Catálogo → Entrega, because the product's real order has a reading step and Generadores and OPUS/Neodata are one deliverable. The line bends down, not up, so it carries every section and ends in a terminus ring at the closing actions. The nav adds Glosario, a Crear cuenta pill and the theme toggle. Rosa marks only the line, the scroll train, the station in view, the primary action and the one traced element (T-3 → EST-12). The line does not draw itself on load: the craft floor wants motion that starts from an already-visible state, and a partial draw read as a broken line in captures. The signature motion is the hero train running the line with station ripples (added 2026-10-27 at Diego's request for a flashier page), plus the numbered scroll train, a moiré op-art emblem in the hero, the plan reading sweep, strikes drawn on scroll and a pulse through the wordmark rings.

ADAPTATIONS 2 (2026-10-27, Diego): the rosa is replaced by a warm naranja tabique accent (brick orange, brown for text, ink text on orange buttons). The hero station map and 1–5 key shortcuts are removed so the page scrolls naturally. The stations are now the app's own tablero (Planos, Disciplinas, Revisión, Catálogo, Presupuesto, Programa), each paired with a drawn, animated app screen of sample data, followed by a team section (presence, change feed, versions).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
