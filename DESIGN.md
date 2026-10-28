---
name: Klave
description: Generadores de obra from structural drawings, every quantity with its evidence. Two visual systems, one per surface family.
colors:
  app-background: "#f7f7f8"
  app-surface: "#ffffff"
  app-surface-2: "#f2f2f3"
  app-surface-3: "#e8e8ea"
  app-foreground: "#161618"
  app-muted: "#5c5c64"
  app-faint: "#6c6c74"
  app-border: "#e6e6e9"
  app-border-strong: "#d2d2d7"
  app-primary: "#18181b"
  app-primary-hover: "#2c2c30"
  app-primary-fg: "#ffffff"
  app-accent: "#2b4acb"
  app-accent-hover: "#223cae"
  app-accent-soft: "#eef1fc"
  app-danger: "#b42318"
  app-danger-soft: "#fbf1f0"
  app-warning: "#935e0c"
  app-warning-soft: "#faf5ea"
  app-success: "#1e7048"
  app-success-soft: "#eff6f1"
  l68-paper: "#fbfbfa"
  l68-ink: "#121212"
  l68-ink-2: "#4a4a50"
  l68-rule: "#dcdcdf"
  l68-accent: "#e8742a"
  l68-accent-hover: "#d9651c"
  l68-accent-text: "#a94a0f"
  l68-accent-fg: "#121212"
  l68-accent-soft: "#fcebdc"
typography:
  app-display:
    fontFamily: "Space Grotesk, Geist, system-ui, sans-serif"
    fontWeight: 600
    letterSpacing: "-0.022em"
  app-headline:
    fontFamily: "Space Grotesk, Geist, system-ui, sans-serif"
    fontSize: "1.4rem"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.022em"
  app-title:
    fontFamily: "Space Grotesk, Geist, system-ui, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 600
    letterSpacing: "-0.022em"
  app-metric:
    fontFamily: "Space Grotesk, Geist, system-ui, sans-serif"
    fontSize: "1.55rem"
    fontWeight: 500
    lineHeight: 1
    fontFeature: "tnum"
  app-body:
    fontFamily: "Geist, system-ui, -apple-system, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    letterSpacing: "-0.004em"
  app-mono:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontFeature: "tnum"
  l68-display:
    fontFamily: "Archivo, Geist, sans-serif"
    fontSize: "clamp(2.6rem, 6.4vw, 6rem)"
    fontWeight: 800
    lineHeight: 0.95
    letterSpacing: "-0.035em"
    fontVariation: "\"wdth\" 112"
  l68-headline:
    fontFamily: "Archivo, Geist, sans-serif"
    fontSize: "clamp(2rem, 4vw, 3.6rem)"
    fontWeight: 800
    lineHeight: 1
    letterSpacing: "-0.035em"
    fontVariation: "\"wdth\" 112"
  l68-title:
    fontFamily: "Archivo, Geist, sans-serif"
    fontSize: "clamp(1.6rem, 2.4vw, 2.2rem)"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.035em"
    fontVariation: "\"wdth\" 112"
  l68-refusal:
    fontFamily: "Archivo, Geist, sans-serif"
    fontSize: "clamp(1.5rem, 3vw, 2.6rem)"
    fontWeight: 750
    lineHeight: 1.08
    letterSpacing: "-0.03em"
    fontVariation: "\"wdth\" 112"
  l68-practice:
    fontFamily: "Archivo, Geist, sans-serif"
    fontSize: "clamp(1.25rem, 2vw, 1.75rem)"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.02em"
    fontVariation: "\"wdth\" 112"
  l68-wordmark:
    fontFamily: "Archivo, sans-serif"
    fontSize: "1.6rem"
    fontWeight: 800
    letterSpacing: "-0.04em"
    fontVariation: "\"wdth\" 125"
  l68-lede:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "clamp(1.06rem, 1.3vw, 1.25rem)"
    fontWeight: 400
    lineHeight: 1.5
  l68-body:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.55
  l68-feature:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.45
  l68-screen:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
    lineHeight: 1.4
  l68-note:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
  l68-caption:
    fontFamily: "Geist, system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
  l68-mono:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    letterSpacing: "0em"
    fontFeature: "tnum"
rounded:
  app-sm: "6px"
  app-md: "8px"
  app-lg: "12px"
  app-full: "999px"
  l68-focus: "2px"
  l68-key-sm: "4px"
  l68-key: "8px"
  l68-pill: "999px"
  l68-ring: "50%"
spacing:
  l68-stroke: "4px"
  l68-pitch: "10px"
  l68-bundle: "34px"
  l68-gutter: "120px"
  l68-pad: "clamp(20px, 4vw, 56px)"
  l68-wrap: "1360px"
  l68-station-block: "clamp(56px, 9vh, 112px)"
  l68-station-gap: "clamp(32px, 5vw, 88px)"
  l68-screen-pad: "clamp(14px, 2vw, 22px)"
  l68-section-block: "clamp(72px, 12vh, 140px)"
components:
  app-button-primary:
    backgroundColor: "{colors.app-primary}"
    textColor: "{colors.app-primary-fg}"
    rounded: "{rounded.app-md}"
    height: "36px"
    padding: "0 14px"
  app-button-primary-hover:
    backgroundColor: "{colors.app-primary-hover}"
  app-button-accent:
    backgroundColor: "{colors.app-accent}"
    textColor: "{colors.app-primary-fg}"
    rounded: "{rounded.app-md}"
    height: "36px"
    padding: "0 14px"
  app-button-accent-hover:
    backgroundColor: "{colors.app-accent-hover}"
  app-button-secondary:
    backgroundColor: "{colors.app-surface}"
    textColor: "{colors.app-foreground}"
    rounded: "{rounded.app-md}"
    height: "36px"
    padding: "0 14px"
  app-button-lg:
    height: "40px"
    padding: "0 16px"
  app-input:
    backgroundColor: "{colors.app-surface}"
    textColor: "{colors.app-foreground}"
    rounded: "{rounded.app-md}"
    padding: "8px 12px"
  app-card:
    backgroundColor: "{colors.app-surface}"
    rounded: "{rounded.app-lg}"
    padding: "16px"
  app-badge:
    rounded: "{rounded.app-sm}"
    padding: "2px 8px"
  l68-button-accent:
    backgroundColor: "{colors.l68-accent}"
    textColor: "{colors.l68-accent-fg}"
    rounded: "{rounded.l68-pill}"
    height: "52px"
    padding: "0 26px"
  l68-button-accent-hover:
    backgroundColor: "{colors.l68-accent-hover}"
  l68-button-line:
    textColor: "{colors.l68-ink}"
    rounded: "{rounded.l68-pill}"
    height: "52px"
    padding: "0 26px"
  l68-button-line-hover:
    backgroundColor: "{colors.l68-ink}"
    textColor: "{colors.l68-paper}"
  l68-button-sm:
    height: "40px"
    padding: "0 18px"
  l68-station-ring:
    backgroundColor: "{colors.l68-paper}"
    rounded: "{rounded.l68-ring}"
    size: "58px"
  l68-station-ring-lit:
    backgroundColor: "{colors.l68-accent}"
  l68-train:
    backgroundColor: "{colors.l68-accent}"
    textColor: "{colors.l68-accent-fg}"
    rounded: "{rounded.l68-pill}"
    width: "46px"
    height: "22px"
  l68-screen-bar:
    textColor: "{colors.l68-ink-2}"
    height: "46px"
    padding: "0 16px"
  l68-screen-body:
    typography: "{typography.l68-screen}"
    padding: "{spacing.l68-screen-pad}"
  l68-tablero-node:
    backgroundColor: "{colors.l68-paper}"
    rounded: "{rounded.l68-ring}"
    size: "11px"
  l68-tablero-node-done:
    backgroundColor: "{colors.l68-ink}"
  l68-tablero-node-now:
    backgroundColor: "{colors.l68-accent}"
  l68-keycap:
    textColor: "{colors.l68-ink}"
    rounded: "{rounded.l68-key}"
    size: "30px"
  l68-screen-chip:
    textColor: "{colors.l68-ink}"
    rounded: "{rounded.l68-pill}"
    padding: "2px 9px"
---

# Design System: Klave

## Overview

**Creative North Star: "Ink and one colour"**

Klave runs two visual systems that share one discipline: ink neutrals carry everything, and exactly one chromatic voice is allowed to speak. In the working application that voice is cobalt and it means "interactive or live data". On the public landing it is naranja tabique, a warm brick orange, and it means "the line": the path of the obra through its stages, and the one thing the page is following. Neither system borrows the other's colour, type or form.

**Which system governs which surface.**

- **The app system ("Ink and Cobalt")** governs every authenticated and workspace surface in `apps/web`: the taller home, every `proyecto/[id]/*` screen, catálogo, equipo, cuenta, compartido, the access screens in `app/(acceso)` (bienvenida, registro, recuperar, restablecer, invitación, verificar), and the explanatory public pages `como-funciona` and `glosario`. Its tokens are the unprefixed custom properties in `apps/web/app/globals.css`, mapped to Tailwind through `@theme inline`; raw hex lives only in that file.
- **The portada world ("Línea 68")** governs only `/portada` (`apps/web/app/portada/page.tsx`, `portada.css`, and `components/portada/`: `RutaPortada.tsx`, `Vistas.tsx`, `Emblema68.tsx`, `MarcaKlave.tsx`). Its colours are the `--l68-*` tokens in `globals.css`; its geometry, type and motion are scoped under `.l68` in `portada.css`. Archivo is loaded by the portada page alone. No other route uses an `l68` class or token.

The app system is dense, quiet and near-monochrome: soft tonal surfaces, hairline borders, small type, a light ambient shadow on cards, Phosphor icons. Línea 68 is large, flat and graphic: a Mexico 68 metro bundle of four parallel strokes runs under the hero, bends down the right edge with rounded metro corners and carries every section to a terminus ring at the closing actions. Six stages sit on it, named after the obra's real tablero (Planos, Disciplinas, Revisión, Catálogo, Presupuesto, Programa); each pairs a drawn, animated screen of the app with its text. Display type is a heavy, expanded grotesk.

**Key Characteristics:**
- Ink neutrals carry both systems; one accent per system (cobalt in the app, naranja tabique on the portada).
- Two committed palettes per system, light and dark, switched by `data-theme` on `<html>`.
- App: Geist body, Space Grotesk display, Geist Mono tabular figures, Phosphor icons, cards with 12px corners.
- Portada: Archivo expanded display, Geist body, Geist Mono tabular measures, a four-stroke metro bundle, station rings, pills, ruled lists, and app screens drawn in ink line instead of screenshots or cards.
- Every figure that is a measure or a key is set in tabular mono in both systems.

## Colors

Near-monochrome in both systems: ink on cool white (or white on near-black in dark mode), with a single accent whose job is fixed.

### Primary
- **Cobalt** (`app-accent`, hover `app-accent-hover`, tint `app-accent-soft`): the app's one accent. Interactivity, focus, selection, live data, the first chart series. Dark mode lifts it to a periwinkle cobalt (`#8296ff`).
- **Naranja Tabique** (`l68-accent`, hover `l68-accent-hover`): the portada's one accent, a warm brick orange. The fourth stroke of the bundle and its corner, both trains, the station ring in view, the terminus ring, the primary action (Crear cuenta), and inside the drawn screens: the current node of the tablero line, the review cursor, the traced element, the one action the screen performs, and the visitor's own presence. It is also the text-selection colour. The 3px focus outline uses Fired Brick (`l68-accent-text`) instead, because the orange fill measures 2.9:1 on light paper, under the 3:1 non-text floor. Dark mode uses `#f08a3e` (hover `#f59d5b`).
- **Fired Brick** (`l68-accent-text`): the accent when it is set as text (the T-3 key, the best catálogo match, the traced programa row, money deltas), a brown that holds 5.5:1 on paper and 4.9:1 on the tint. In dark mode it is the accent itself (`#f08a3e`, 7.8:1 on dark paper).
- **Ink on Tabique** (`l68-accent-fg`): text on any orange fill (buttons, train number, selection, the "TÚ" avatar). It is ink, not white: white on the orange is 3.0:1. Dark mode uses dark paper `#0d0d0e`.
- **Tabique Tint** (`l68-accent-soft`): the fill behind the traced element and the action being taken (the selected T-3 beam, the T-3 review row, the "Del plano" source block in Catálogo, the proposed action in Presupuesto). Dark mode `#2a1a0e`.

### Neutral
- **App Ink** (`app-primary`, `app-primary-hover`, `app-primary-fg`): the app's action colour. Primary buttons and brand emphasis are ink, not cobalt. Dark mode inverts it to light ink on dark ground.
- **App Ground and Surfaces** (`app-background`, `app-surface`, `app-surface-2`, `app-surface-3`): page ground, cards and inputs, hover fills and table heads, the deepest tonal step.
- **App Text** (`app-foreground`, `app-muted`, `app-faint`): primary, secondary and tertiary text; muted and faint both pass AA on ground and surfaces.
- **App Borders** (`app-border`, `app-border-strong`): hairlines and their hover / focus step.
- **Semantic tones** (`app-danger`, `app-warning`, `app-success` and their `-soft` tints): desaturated; badge and callout fills use the tint with the tone as text.
- **Paper** (`l68-paper`): the portada ground, the inside of station rings and pending tablero nodes, the knockout halo around both trains, the gaps in the button outline rings.
- **Línea Ink** (`l68-ink`): portada text, the three ink strokes of the bundle, ring strokes, the 2px frame of every drawn screen, done tablero nodes, list rules of weight 2px, the plan drawing, programa bars, keycaps.
- **Second Ink** (`l68-ink-2`): ledes, notes, stage numbers, captions, breadcrumbs and secondary text inside the screens.
- **Rule** (`l68-rule`): 1px separators between list rows, screen rows and sections; the empty track behind score bars.

Dark counterparts (portada): paper `#0d0d0e`, ink `#f1f1ef`, ink-2 `#a9a9af`, rule `#2a2a2f`.

### Named Rules
**The One Voice Rule.** Each system has exactly one chromatic accent. Cobalt never appears on the portada; naranja tabique never appears in the app.

**The Line Owns the Accent Rule.** On the portada, naranja tabique marks only the line (fourth stroke, corner, trains, the lit and terminus rings), the primary action, focus and selection, and inside a drawn screen the stage it is on, the traced element (T-3 → EST-12), the one action being performed and the money it moved. Secondary actions, chips, verdicts, tables and headings stay ink. Status inside a screen is drawn in ink (solid, outlined, dashed), never coloured.

**The Ink on Tabique Rule.** Text on an orange fill is ink (`l68-accent-fg`); orange as text is fired brick (`l68-accent-text`). Never white on orange, never the raw accent as light-mode text.

**The Ink Action Rule.** In the app, the primary button is ink; cobalt is for interactivity and data, not for the main call to action.

## Typography

**Display Font:** Space Grotesk (app, `h1`–`h3` and metrics); Archivo variable at expanded width (portada)
**Body Font:** Geist (both systems)
**Label/Mono Font:** Geist Mono with tabular figures (both systems)

**Character:** The app pairs a compact technical grotesk with a neutral sans at small, dense sizes. The portada sets Archivo heavy and widened (width axis 112% for headings, 125% for the wordmark) and tight, against plain Geist body copy.

### Hierarchy
- **Portada display** (`l68-display`): the hero headline, capped at 13ch, balanced wrap.
- **Portada headline** (`l68-headline`): section headings (refusals, practice, closing), capped at 16ch. The team section uses the same face one step down (`clamp(1.8rem, 3vw, 2.6rem)`).
- **Portada title** (`l68-title`): stage headings.
- **Portada refusal / practice** (`l68-refusal`, `l68-practice`): the struck refusals and the practice list, expanded Archivo at their own sizes.
- **Portada lede / body / feature** (`l68-lede`, `l68-body`, `l68-feature`): ledes capped at 54ch, stage paragraphs at 44ch in second ink, feature list rows.
- **Portada screen** (`l68-screen`): all text inside the drawn app screens; bars, chips and captions at `l68-caption`, inline keys and verdicts smaller.
- **Portada note / caption** (`l68-note`, `l68-caption`): the approval note under the hero actions; screen captions and breadcrumbs.
- **Portada mono** (`l68-mono`): sheet keys, marks, claves, ejes, hojas, quantities, money, stage numbers (`01`–`06`), the train's number.
- **App headline** (`app-headline`): page titles. **App title** (`app-title`): section titles. **App metric** (`app-metric`): stat values in Space Grotesk with tabular figures.
- **App body** (`app-body`): the 15px interface base; secondary text in `text-sm` muted.

### Named Rules
**The Expanded Grotesk Rule.** Portada display text is Archivo with `font-stretch` 112% (125% for the wordmark), weight 700–900, negative tracking between -0.02em and -0.04em. The shipped `Archivo.woff2` carries the width axis (62–125) and weight axis (100–900). Inside the drawn screens Archivo appears only on the inspector's T-3 mark; everything else, the Presupuesto total included, is Geist and Geist Mono, as in the app.

**The Tabular Measure Rule.** Every key, clave, eje, hoja, quantity and amount is set in Geist Mono with tabular figures.

## Layout

**App.** Tailwind spacing on a 4px base; cards pad at 16px; page headers sit above content with 24px below; controls step 32 / 36 / 40px tall (sm / md / lg), with 40px reserved for single-task forms (access, new project) where buttons match 40px inputs. Data views are dense: sticky tables, stat strips, rails.

**Portada.** A single column wrapper capped at 1360px with fluid side padding (`l68-pad`). The hero is the headline, lede and actions on the left with the op-art emblem at the right (1180px and wider); there is no station map row. The horizontal bundle runs full bleed under the hero and bends down the right edge; the route reserves a 120px right gutter (`l68-gutter`) for the vertical bundle. Order below the hero: six stages, the team section ("Tu equipo, en la misma obra"), refusals, practice, the closing actions on the terminus ring, the wordmark, the footer.

Each stage is a two-column grid: the drawn screen on the left (1.55fr), the text on the right (1fr), gap `l68-station-gap`, block padding `l68-station-block`. The text is the two-digit stage number in mono second ink, the heading, a paragraph and a ruled feature list. The team section uses the same grid. Refusals are a two-column ruled list (1.35fr / 1fr); practice is a two-column list. Larger sections use `l68-section-block`. Sections are separated by 1px rules, not by background changes.

Bundle geometry is exact: four strokes 4px wide on a 10px pitch make a 34px bundle; the corner bends down with radii 100 / 90 / 80 / 70 so the vertical strokes land at 0 / 10 / 20 / 30px from the right edge. Station rings (58px) are centred on the vertical bundle, level with the stage heading.

Below 860px the line runs down the left: the horizontal bundle, corner and hero train are hidden, the gutter collapses, the vertical bundle moves to a 64px left track, stages stack in one column with the text above its screen and the ring (52px) on the line, and the visor's inspector drops under the plan. Below 560px the screens shed the "Obra de ejemplo /" crumb, long labels and secondary columns rather than shrinking type.

### Named Rules
**The Four Strokes Rule.** The line is always a bundle of four equal 4px strokes on a 10px pitch: three ink, one naranja tabique. Bends are concentric arcs, never mitred corners.

**The Screen Left Rule.** A stage shows the product first: the drawn screen takes the wider left column and the words sit to its right. On narrow screens the words come first so the screen is read with its caption.

## Elevation & Depth

**App.** Lightly layered: tonal surfaces do most of the work, and cards carry an ambient shadow that deepens on hover.

### Shadow Vocabulary
- **Rest** (`--shadow-xs`, `0 1px 2px rgba(22, 22, 24, 0.05)`): cards at rest.
- **Small** (`--shadow-sm`): range-slider thumb and small raised controls.
- **Hover** (`--shadow-md`, `0 2px 6px -1px rgba(22, 22, 24, 0.06), 0 8px 20px -6px rgba(22, 22, 24, 0.1)`): interactive cards on hover.
- **Overlay** (`--shadow-lg`): menus, dialogs, floating panels.

**Portada.** Completely flat. No element casts a shadow. `box-shadow` appears only as a drawing technique: zero-blur spread rings that outline the secondary button, keycaps, chips, verdicts, format pills and the review cursor; the 68 outline rings buttons grow on hover; and a paper-coloured knockout ring (4px on the scroll train, 3px on the hero train) that separates a train from the strokes beneath it. The drawn screens are framed by a 2px ink border with no fill, no radius and no shadow.

### Named Rules
**The Flat Line Rule.** On the portada, depth is drawn with strokes and knockouts, never cast. If a `box-shadow` has a blur or an offset, it does not belong on the portada.

## Shapes

**App.** Gently rounded: 6px for badges, icon buttons and the focus outline; 8px for buttons, inputs and callouts; 12px for cards and empty states; full rounding for avatars, dots and slider thumbs.

**Portada.** Two shapes from the metro map: the full pill (buttons, trains, chips, verdicts, tool toggles, programa bars) and the circle (station rings with a 5px ink stroke, the 11px tablero nodes with a 2px stroke, the 30px avatars). Drawn screens are square-cornered rectangles in a 2px ink line. Keycaps are the exception: 8px corners at 30px (Revisión), 4px for inline keys. Lists are open ruled rows: a 2px ink rule on top where a list opens, 1px rules between rows. A pending verdict or a "por revisar" chip is drawn with a 1.5px dashed ink border.

The feature-list bullet is the line's own mark: two short parallel strokes, 14px wide and 2px thick on a 5px pitch, ink above and naranja tabique below.

The wordmark at the foot is "Klave" in Archivo 900 at 125% width, drawn as seven concentric layers (alternating ink and paper strokes of 74 / 62 / 50 / 38 / 26 / 14px, then the ink fill), the Mexico 68 lettering device.

## Components

### Buttons
- **App shape:** gently rounded (8px), medium weight, colour transition only.
- **App primary:** ink fill, white text; hover steps to the lighter ink.
- **App accent:** cobalt fill, white text, for the cases where the action is the live-data action.
- **App secondary / ghost / danger:** surface with hairline border (hover: stronger border, surface-2 fill); muted text on no fill (hover: surface-2); danger tint with danger text.
- **Portada shape:** full pill, 52px tall (40px small in the nav), weight 650.
- **Portada primary:** naranja tabique fill, ink text, a Phosphor ArrowRight that slides 3px on hover; hover deepens the orange.
- **Portada line:** a 2px inset ink stroke, ink text; hover fills ink with paper text.
- **Both:** press nudges 1px down on the portada; focus is the system's outline (app: 2px cobalt ring at 2px offset; portada: 3px naranja tabique at 3px offset, except buttons, which show their outline rings instead).

### Chips
- **App badge:** 6px corners, tint fill with tone text, optional dot.
- **Portada screen chips** (provenance, vigencia, «Sin precio», format tags, sheet destinations): pills drawn with a 1.5px inset stroke and no fill. Status is drawn, not coloured: ink outline for confirmed or vigente, dashed for por revisar or en duda, a 2px bold outline for «Sin precio», solid ink with paper text for excluded, Bloqueante and the sheets read in depth.

### Cards / Containers
- **App:** surface fill, 1px border, 12px corners, rest shadow, 16px padding; interactive cards deepen border and shadow on hover.
- **Portada:** none. The containers are drawn screens (below), ruled lists, and captioned figures.

### Inputs / Fields
- **App:** surface fill, 1px border, 8px corners, 8px by 12px padding; focus strengthens the border and adds a 2px cobalt ring; placeholders in faint. Access forms use 40px fields.

### Navigation
- **App:** workspace header and project shell in app tokens; tab strips scroll sideways with an inset 1px baseline and no visible scrollbar.
- **Portada:** 84px bar, expanded Archivo wordmark left; text links (Cómo funciona, Glosario, Entrar) draw a double 1.5px underline on hover and focus; a small naranja tabique Crear cuenta pill and the theme toggle at the right. Below 860px, Cómo funciona, Glosario and the toggle are hidden.

### Feature List (portada)
The ruled list beside each stage: rows at the feature size with 11px block padding, a 1px rule above each row, 26px indent for the two-stroke bullet (ink over naranja tabique).

### Drawn App Screen (signature, portada)
An illustration of a real app screen, built in the portada's own language rather than a screenshot. A 46px bar framed in 2px ink holds the breadcrumb ("Obra de ejemplo / {screen}", the screen name in ink 650) and, at the right, the obra's tablero as a mini line of six 11px nodes joined by 2px ink links: done nodes are filled ink, the current node is filled naranja tabique, later nodes are paper. The body sits under it in the same 2px frame, without a top border. Every screen carries sample data and a second-ink caption ("Pantalla ilustrativa con datos de ejemplo."; the team screen: "Pantalla ilustrativa: nombres y montos de ejemplo."). The tablero line carries an accessible label ("Etapa n de 6: …").

Each screen plays a CSS sequence once and ends on its finished state, which is also what shows without script or under reduced motion. Screens that start below the fold are held at their first frame (`animation-play-state: paused`) until 35% of them is visible; figures marked for counting tick up from zero when the screen plays.
- **Planos:** the upload arrow drops in, six sheets arrive one by one (220ms apart), each shows "Leyendo…" and then pops its destination (Estructura in solid ink, Levantamiento outlined, the architectural background marked "no se cobra"), and the summary line lands last.
- **Disciplinas (visor):** a 6px naranja tabique scan bar sweeps the plan; zapatas, then trabes, then castillos appear in sequence; T-3 is picked (its stroke swells and settles in the accent over the tint); the inspector rows (marca, familia, sección, ejes, longitud, hoja, lectura) slide in.
- **Revisión:** a 2px naranja tabique cursor steps down the queue row by row; the C, X and Q keycaps flash ink as each verdict pops in (confirmed outlined, excluded solid with its reason, en duda dashed); the counter runs to 5 de 5, and the stage-closed lock line arrives last.
- **Catálogo:** three suggestions arrive with their match bars growing (the best, EST-12, in the accent); "Adoptar EST-12" appears, is pressed and gives way to "Adoptada · Klave la recuerda…"; provenance rows follow.
- **Presupuesto:** the direct cost counts up; a Bloqueante finding shows its proposed action on the tint; "Aplicar" is pressed and becomes "Aplicado"; the blocker count swaps from 1 to 0, the finding dims, the total counts to its corrected value with the ▲ delta, and "Exportar bloqueado…" gives way to "Listo para exportar" as the format pills unlock.
- **Programa:** seven bars are laid along ten weeks (the traced "Trabes nivel 1" bar in the accent), then the cash curve draws itself and the estimación marks fade in.
- **Equipo:** three avatars arrive (the visitor's own, "TÚ", in the accent), then four changes stream into the feed with the amount each moved.

### Station Ring and Trains (signature, portada)
A 58px circle, paper inside a 5px ink stroke, sitting on the line beside each stage. The stage in view lights its ring naranja tabique; the terminus ring at the closing actions is always lit. Rings are drawn, not controls. The scroll train is a 46 by 22px naranja tabique pill with a paper knockout that rides the vertical bundle to the reading position as the page scrolls (120ms linear) and carries the stage number in view (Geist Mono 11px bold, ink on orange).

### Portada motion (only when motion is allowed)
- **Hero train (the focal moment):** a 44 by 12px naranja tabique pill with a 3px paper knockout runs the accent stroke along an `offset-path` (rotating with the path) without stopping, rounds the bend and fades into the vertical bundle. It travels at 0.9px per ms on `cubic-bezier(0.45, 0, 0.2, 1)`, starts 400ms after the route enters the viewport and repeats every 8s while it stays in view. Hidden under 860px.
- **Station ripple:** two 3px naranja tabique rings spread from a station ring (scale 1 → 2.2, 1000ms, the second 160ms later) when its stage becomes the one in view.
- **Drawn screens:** the sequences above, on the shared ease-out, with whole counts ticking linearly and money easing out.
- **Op-art emblem:** two sets of twelve concentric 6px ink rings (radii 10–241) in the hero's right column. The top set orbits 12px in 16s and follows the pointer up to 26px, which makes the 1968 moiré. Shown at 1180px and wider, paused off screen, static and offset under reduced motion.
- **Refusal strikes:** where `animation-timeline: view()` exists, the strike is a background line drawn left to right as the refusal scrolls in. Elsewhere it is a plain `line-through`.
- **Wordmark pulse:** while on screen, a naranja tabique pulse runs outward through the wordmark's ink rings (3.6s cycle, 180ms between rings). The letters stay ink.
- **Controls:** on hover and focus, buttons grow their own 68 outlines (paper 3px, accent 5px, paper 8px, accent 10px; ink for the secondary button) over 320ms. Nav links draw a double 1.5px underline.

### Traced Element (signature, portada)
The single element the page follows from drawing to deliverable: the T-3 beam picked in the Disciplinas plan (accent stroke over the tint, its mark in fired brick in the inspector), its row on the tint in Revisión, the "Del plano · Trabe T-3" block on the tint in Catálogo with EST-12 as the best match, its delta in Presupuesto and in the team feed, and the "Trabes nivel 1" bar in Programa. Every other row and drawing element is ink.

## Do's and Don'ts

### Do:
- **Do** decide the system by surface first: `/portada` is Línea 68; every other route, including access screens, como-funciona and glosario, is the app system.
- **Do** take portada colours only from the `--l68-*` tokens and keep portada geometry, type and motion scoped under `.l68`.
- **Do** draw the portada line as four 4px strokes on a 10px pitch, three ink and one naranja tabique, with concentric rounded bends.
- **Do** set every key, eje, hoja, quantity and amount in Geist Mono with tabular figures.
- **Do** use `l68-accent-text` whenever the accent is set as text, and `l68-accent-fg` (ink) for text on an orange fill.
- **Do** show the product as drawn screens in the portada's ink line, with sample data, a caption that says so, and a sequence that ends on the finished state.
- **Do** draw status inside a screen with ink (solid, outlined, dashed, bold outline), leaving the accent for the stage, the traced element and the action.
- **Do** keep app primary actions ink and reserve cobalt for interactivity, focus and live data.
- **Do** honour `prefers-reduced-motion`: the portada drops the trains' travel, the ripples, the screen sequences and counters (screens show their finished state), the emblem drift, the drawn strikes and the wordmark pulse; the app disables its entry and flow animations.

### Don't:
- **Don't** use naranja tabique on the portada for anything other than the line, the trains, the lit or terminus station, the primary action, focus and selection, and inside a screen the current stage, the traced element, the action being performed, the money it moved and the visitor's own presence.
- **Don't** put cards, icon tiles, colour gradients or cast shadows on the portada; inset strokes, the paper knockout and hard-stop gradients that draw a stroke (the bullet, the nav underline, the strike) are line drawing, not elevation or colour gradients.
- **Don't** put screenshots on the portada; the product is shown as drawn screens.
- **Don't** use eyebrows or kickers above portada headings; the only text above a stage heading is its two-digit number.
- **Don't** set white text on the orange or the raw accent as light-mode text.
- **Don't** carry Archivo, naranja tabique or the bundle into the app, or cobalt, Space Grotesk and cards onto the portada.
- **Don't** write raw hex outside `apps/web/app/globals.css`.
