# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

The whole team of a Mexican construction office («taller»), with no single role above the others:

- **Cost engineers (ingenieros de costos)** prepare bids: they read a plan set, build the generadores de obra, price them against the office's catálogo, and finish the budget in OPUS or Neodata.
- **The office admin** approves accounts and invitations, keeps the catálogo and prices current, and locks a project's stages once they are settled.
- **Reviewers** confirm or exclude what the engine read from the drawing and sign the verification, often more junior engineers working through the review queue by keyboard.

Everyone signs or answers for what the screen says: a quantity in Klave ends up in a bid someone is accountable for.

## Product Purpose

An office drops in a plan set (DWG or DXF) and gets generadores de obra negra in which every quantity is linked to where it is on the drawing, mapped onto the office's own catálogo, and exported into OPUS or Neodata. Klave feeds the tools the office already uses; it does not replace them.

Beyond the bid, the same project carries on to programa de obra, cash flow and estimaciones, worked collaboratively in real time.

Success is measured by the pilot gate: one real bid done in Klave beside the old way, compared on hours saved, generadores the office accepts, and an export that imports cleanly into OPUS or Neodata.

## Positioning

Klave is built to be sold to many Mexican contractors and offices; the pilot office is the first customer.

What a neighbouring product cannot truthfully claim:

- The drawing is read by deterministic detectors (CPU only), and every quantity carries its evidence and its assumptions.
- **Nothing is invented.** A quantity without a trustworthy unit is never shown as money, a concept without a price stays visible as a gap and never as $0, and one authority decides each verdict.
- Mexican practice is first-class, not translated: EJES / TRABES / CASTILLO / ZAPATA conventions, RLOPSRM (salario real, costo horario), official price publications (CDMX, SICT, CONAGUA, Chiapas, Guanajuato), and native OPUS / Neodata import and export.

## Operating Context

- **Where:** office desktops with large screens and long working sessions. Phones are used only to check status or sign in.
- **Inputs:** plan sets of up to 40 DWG/DXF sheets per project. Structural is read in depth; other disciplines are read as honest counts («levantamiento»), and the architectural background is shown but never charged.
- **Outputs:** generadores, budget, programa de obra, cash flow, estimaciones; XLSX generadores and OPUS / Neodata exports.
- **Workspace model:**
  - Each office is a workspace («taller») with admin and member roles, and per-project viewer / editor / owner access.
  - People join by invitation, or register and wait for an admin's approval.
  - Each project is a node board in process order (Planos → Disciplinas → Revisión → Catálogo → Presupuesto → Programa), each node with an admin lock.
- **Tools beside Klave:** OPUS, Neodata, Excel, and the office's drawing software (DWG exported to DXF when conversion fails).

## Capabilities and Constraints

- **Product language:** Spanish (es-MX). Every interface string, error and document is Spanish; terminology follows Mexican cost-engineering usage.
- **Stack in place:** Next.js web app (`apps/web`) over a FastAPI engine (`apps/api`, `klave_engine`); separate Postgres for accounts. The production API runs on AWS EC2 and the web on Vercel.
- **Modes:** open (local, no accounts) and protected (accounts and roles enforced). Passwords are at least 10 characters, with the same policy on register, reset and invitation.
- **Assistance:** a copilot acts on review findings through previewed, deterministic actions; a guided tour teaches the full path on a per-user sample project.
- **Undecided:** pricing and the business model; the generalising ML reader (rules, a small model, a large model for the long tail, per-office convention profiles) is specified but still in progress.

## Brand Commitments

- **Name:** Klave.
- **Voice:** plain, professional Spanish that names exactly what is known, what is not, and how sure it is. «Sin precio», never $0.
- **Standing direction for the interface:** «less colours, less distraction, sharp and expensive».
- **Written interface rule:** `docs/principios-de-interfaz.md` (Honestidad, Severidad, Legibilidad, in that order of precedence).

## Evidence on Hand

- **Gold set** (`evals/gold`): engine-captured baselines used for regression only, not for accuracy, and with no money in them.
- **Real drawings** used to tune the reader: PRUEBA-1 and Marina-4.
- **Official price sources:** CDMX, SICT, CONAGUA, Chiapas, Guanajuato (`data/sources`).
- **Not yet in hand, and not to be fabricated:**
  - pilot results;
  - customer names or testimonials;
  - accuracy claims or benchmarks against engineer-confirmed ground truth;
  - time-saved figures;
  - pricing.

## Product Principles

1. **Nothing is invented.** Every number shows its source and its assumptions; what is unknown stays visibly unknown, and confidence is never dressed up as precision.
2. **Severity before reading.** What can cost money is set apart from what cannot, before anyone has to read everything.
3. **Feed the office's tools.** Klave fits the office's catálogo, its conventions, and OPUS / Neodata; the office should never have to change how it closes a bid.
4. **The team answers together.** Reviews, locks and verifications carry an author, because the result is signed by people.
5. **Mexican practice is native.** Terms, norms and formats are the ones an ingeniero de costos in Mexico already uses.
