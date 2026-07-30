# Mexico-First Cost Data Platform Design

**Status:** Proposed for implementation after written-spec approval

**Date:** 2026-07-30

**Product scope:** Multi-tenant cost-data foundation for complete obra negra, with structural work as the first and deepest vertical

**Initial market:** Ciudad de México, followed by state-level Mexican price books

## 1. Context

Klave currently derives seven structural cost concepts from deterministic drawing
analysis and hard-coded Python data. It has no durable catalog database, catalog
versioning, tenant isolation, source provenance, price-observation model, import
workflow, or approval state.

The supplied spreadsheets are useful seeds:

- a labor-productivity catalog with approximately 330 valid rendimientos;
- Centro, Sur, and Norte labor catalogs with approximately 330 APU matrices each;
- a 2,698-concept composite unit-price catalog covering foundations, structure,
  masonry, finishes, and installations; and
- a project-specific structural quantity workbook containing useful formulas and
  several broken references.

These sources cannot be treated as a trusted CDMX price book without additional
provenance, dates, geography, cost-basis metadata, and market corroboration.

This project is larger than one implementation cycle. It is decomposed into:

1. **This specification:** canonical cost-data platform, Excel/CSV ingestion,
   tenant-scoped catalogs, CDMX baseline acquisition, validation, versioning, and
   price resolution.
2. **Follow-on specification:** drawing intelligence, canonical geometry,
   evidence graph, measurement rules, and geometric validation.
3. **Follow-on specification:** obra-negra takeoff orchestration, APUs, schedule,
   financial projections, approval controls, and issued-budget snapshots.
4. **Follow-on specification:** production hardening, hosted deployment,
   authentication, observability, data lifecycle, and operational controls not
   completed by the earlier projects.

The cost-data platform comes first because geometry cannot produce a defensible
budget if pricing and APU inputs are opaque or unversioned.

## 2. Decisions Already Approved

- Mexico is the first market.
- CDMX is the first calibration market.
- Other Mexican regions begin at state-level precision.
- The commercial scope is complete obra negra with a primary structural focus.
- Klave provides a regional baseline and supports private BYOC catalogs.
- Excel and CSV are the v1 interchange formats.
- OPUS and Neodata are deferred adapters over the canonical model.
- The product is multi-tenant.
- Ordinary estimates may be self-approved.
- Estimates marked controlled require approval by a different authorized user.
- Existing spreadsheets are seed data, not trusted production truth.

## 3. Goals

### 3.1 Product goals

- Turn cost data into a durable, versioned product asset.
- Produce reproducible budgets whose quantities and prices can be traced to
  evidence, formulas, source documents, and approvals.
- Let organizations use Klave's CDMX/state books, private catalogs, project
  quotations, or a controlled combination.
- Make spreadsheet import safe enough that invalid data cannot silently enter an
  issued estimate.
- Improve the existing prototype immediately while confidence increases over
  time.

### 3.2 Technical goals

- Introduce PostgreSQL as the system of record for shared product and tenant data.
- Preserve immutable raw imports and immutable published catalog versions.
- Use one canonical domain model regardless of source format.
- Enforce tenant isolation in application code, database constraints, and
  PostgreSQL row-level security.
- Keep Decimal money, typed quantities, explicit units, and explicit tax basis at
  every financial boundary.
- Resolve prices deterministically with no silent zero-price fallback.
- Preserve the existing immutable drawing-run artifacts while allowing catalog
  and run metadata to reference database records.

## 4. Non-Goals

The first implementation does not:

- provide OPUS or Neodata import/export;
- scrape retailer sites as the primary acquisition method;
- infer trustworthy dates or geography from filenames;
- redistribute licensed commercial data without explicit rights;
- replace professional estimator or engineer review;
- implement a generalized event-sourcing platform;
- rebuild the drawing detectors;
- complete the schedule or financial-projection engines; or
- validate all 2,698 seed concepts before the first useful release.

## 5. Recommended Architecture

Klave remains a modular monolith. The current Python engine and FastAPI service
gain a cost-data domain rather than a separate microservice.

```text
Excel / CSV / official source / supplier quote
                |
                v
        Immutable source document
                |
                v
       Import parser and row staging
                |
                v
   Mapping -> normalization -> validation
                |
        +-------+--------+
        |                |
        v                v
   Quarantine       Reviewable diff
                         |
                         v
                Approved catalog version
                         |
                         v
   Project quote -> Org catalog -> Klave CDMX -> state book
                         |
                         v
                 Deterministic price resolution
                         |
                         v
             Reproducible budget snapshot
```

### 5.1 Runtime components

- **PostgreSQL:** catalog, price, tenancy, approval, and audit system of record.
- **SQLAlchemy 2 and Alembic:** persistence and controlled schema migration.
- **Pydantic domain contracts:** API and service boundaries.
- **Object-storage abstraction:** source files and generated import reports.
  Development uses an explicit local directory; production uses private
  S3-compatible storage.
- **FastAPI cost-data module:** import, review, publication, catalog query, and
  price-resolution endpoints.
- **PostgreSQL-backed import jobs:** a separate worker claims jobs with
  `FOR UPDATE SKIP LOCKED`; no Redis or Celery dependency is introduced in this
  cycle. Import progress is published through the existing event/SSE transport.
- **Next.js catalog workspace:** import mapping, validation, diff, approval,
  catalog browsing, and provenance inspection.

Database entities are never written directly by route handlers. Routes call
domain services; services use tenant-aware repositories.

## 6. Tenancy and Authorization

### 6.1 Ownership scopes

Every catalog-like record has one explicit ownership scope:

- `platform`: Klave-managed regional baseline;
- `organization`: private BYOC master catalog; or
- `project`: quotations and project-specific overrides.

Tenant-owned tables include a non-null `organization_id`. Project-owned records
also include `project_id`. Platform records have a platform owner and are
read-only to customer roles.

### 6.2 Roles

- **Owner/Admin:** membership, organization settings, catalog policy, and all
  approvals.
- **Estimator/Editor:** import, map, correct, and prepare catalog and budget
  drafts.
- **Approver:** approve catalog versions and controlled estimates.
- **Viewer:** read published catalogs and issued estimates.

The same person may prepare and approve an ordinary estimate when organization
policy allows it. A controlled estimate rejects approval when `approved_by` is
the same user as `prepared_by`.

### 6.3 Isolation controls

- Hosted environments authenticate signed JWTs from a configured OIDC issuer.
  Klave stores organization membership and role assignment, not passwords.
- A development identity override is allowed only when the application is
  explicitly running in local-development mode; startup fails if it is enabled
  in a hosted environment.
- Tenant context is derived from authenticated membership, never accepted as an
  unrestricted request field.
- All tenant uniqueness constraints include `organization_id`.
- Repository methods require tenant context.
- PostgreSQL row-level security reads the organization identifier set on the
  transaction and provides defense in depth.
- Background jobs carry signed tenant context and revalidate authorization.
- Source-file downloads use short-lived authorized URLs.
- Cross-tenant access tests are mandatory for every tenant-owned endpoint.

## 7. Canonical Domain Model

Internal UUIDs are the durable identities. Source codes such as `DC1-PRE-TN-01`,
`S1-PRE-TRA-01`, and customer codes are aliases, not global primary keys.

### 7.1 Source and import records

- **SourceDocument**
  - ownership scope and tenant;
  - original filename, MIME type, byte size, and SHA-256;
  - storage location;
  - source organization and source URL when applicable;
  - licensing/usage-rights classification;
  - asserted geography and effective date;
  - uploader and upload timestamp.
- **ImportBatch**
  - selected parser/template;
  - mapping configuration;
  - parser and validation-rule versions;
  - status and row counts;
  - source document;
  - reviewer and publisher.
- **StagedRow**
  - source sheet and exact row/cell locators;
  - raw values;
  - normalized candidate;
  - validation findings;
  - disposition: accepted, corrected, quarantined, or ignored.

### 7.2 Taxonomy and units

- **WorkCategory:** hierarchical Mexican construction taxonomy.
- **Concept:** delivered work, independent of a particular source code or price.
- **ConceptAlias:** source-specific code and description mapped to a concept.
- **UnitDefinition:** canonical code, dimension, display name, conversion factor,
  and whether conversion is context-free.
- **UnitAlias:** normalized spellings such as `M2`, `m²`, and `metro cuadrado`.
- **Region:** country, state, and optional CDMX alcaldía/market zone.

V1 canonical units include length, area, volume, mass, count, hour, crew-day,
service, lot, outlet, trip, and percentage-of-explicit-base. Context-free unit
conversion is allowed for `kg <-> t`, but never for incompatible dimensions or
ambiguous construction units.

### 7.3 Resources, crews, and APUs

- **Resource**
  - type: labor, material, equipment, subcontract, tool, auxiliary, or waste;
  - technical specification and canonical purchasing unit.
- **Crew**
  - versioned composition of labor resources and quantities.
- **Rendimiento**
  - output quantity per crew-day;
  - conditions, unit, source, confidence, and effective period.
- **APU**
  - concept, output unit, output quantity, geography, effective period, source,
    status, and version.
- **APUComponent**
  - resource, crew, or nested basic cost;
  - coefficient, waste factor, unit, and calculation basis.

APU dependency graphs must be acyclic. Percentage components must identify their
base explicitly, such as labor subtotal; a unit string like `(%)MO` is not enough.

### 7.4 Prices and price books

- **PriceObservation**
  - resource or concept;
  - Decimal amount and currency;
  - original and canonical unit;
  - geography;
  - observed, effective, expiration, and ingestion dates;
  - IVA inclusion and tax profile;
  - freight, delivery, pumping, minimum-order, and payment conditions;
  - source document and exact locator;
  - confidence grade and approval status.
- **PriceBook**
  - platform, organization, or project ownership;
  - region and intended cost basis.
- **PriceBookVersion**
  - immutable approved or published snapshot with effective dates and approver.
- **PriceBookEntry**
  - selected observation or computed APU result plus the full selection reason.

Money uses fixed-scale Decimal storage. Floating-point values are not accepted at
financial boundaries.

Catalog-version lifecycle is `draft -> validated -> approved -> published ->
superseded`. A published version is immutable. A reference-only Seed import may
remain queryable for prototype comparison but cannot enter the `published`
state.

### 7.5 Mapping from drawings to costs

This project only defines the interface:

- **MeasurementRuleRef:** versioned identifier for the future geometric
  measurement rule.
- **ConceptMapping:** detected assembly family plus specification predicates maps
  to one or more candidate concepts/APUs.

Mappings never choose a concept solely from a free-text similarity score. A
future measurement engine must supply compatible element type, quantity
dimension, material/specification evidence, and confidence.

## 8. Excel and CSV Import Workflow

V1 accepts `.xlsx` and UTF-8 CSV. It does not accept legacy `.xls`, macro-enabled
`.xlsm`, password-protected workbooks, or executable content.

### 8.1 Stages

1. **Upload**
   - enforce size and type limits;
   - scan for malware;
   - compute SHA-256;
   - store the original file immutably;
   - detect duplicate uploads within the same organization.
2. **Parse**
   - enumerate sheets and used ranges;
   - preserve raw values, displayed values, and formula text;
   - never execute spreadsheet macros;
   - flag external links and broken formula values.
3. **Template detection**
   - recognize Klave's documented templates;
   - recognize supported seed schemas;
   - otherwise require interactive column mapping.
4. **Mapping**
   - user selects semantic fields;
   - unit, geography, currency, tax basis, effective date, and price basis must
     be mapped or explicitly supplied as batch-level assertions.
5. **Normalization**
   - normalize Unicode, whitespace, units, Decimal values, dates, and source
     codes;
   - preserve every raw value alongside the normalized value.
6. **Validation**
   - apply row-level and cross-row domain rules;
   - recompute totals server-side;
   - identify duplicates and potential equivalents;
   - classify findings as blocking, warning, or informational.
7. **Diff and review**
   - compare with the selected catalog version;
   - display additions, changes, retirements, conflicts, and quarantined rows;
   - require explicit correction or acknowledgement.
8. **Publish**
   - create a new immutable catalog version;
   - attach the import batch, findings, approver, and publication timestamp;
   - never mutate the prior published version.

No import may publish automatically merely because parsing succeeded.

### 8.2 Formula policy

- Formula text and cached display values are preserved for evidence.
- Klave recomputes arithmetic fields such as `quantity * unit_price`.
- External workbook references are blocking findings.
- Spreadsheet errors such as `#REF!`, `#VALUE!`, `#NAME?`, and `#DIV/0!` are
  blocking for affected rows.
- Unsupported formulas never become trusted computed values.
- CSV cells beginning with formula-control characters are escaped on export to
  prevent spreadsheet injection.

### 8.3 Klave templates

Klave publishes separate, documented templates for:

- concepts and aliases;
- resources and price observations;
- crews and members;
- rendimientos;
- APUs and components; and
- supplier quotations.

Templates include stable field IDs in addition to Spanish display labels so that
renamed columns remain mappable.

## 9. Validation Policy

### 9.1 Blocking rules

- missing tenant, source, currency, geography, unit, or effective date where
  required;
- non-finite, zero, or negative price where a price is expected;
- zero or negative rendimiento;
- dimensional mismatch;
- unknown unit without an approved mapping;
- duplicate active source code in the same catalog version;
- incompatible duplicate concept candidates;
- APU cycle;
- percentage component without an explicit base;
- arithmetic mismatch outside configured Decimal rounding tolerance;
- invalid date range or expired quotation selected as current;
- unknown IVA inclusion or direct/indirect cost basis for a publishable price;
- unresolved external spreadsheet reference; or
- source usage rights incompatible with the intended publication scope.

### 9.2 Warning rules

- statistically unusual normalized price;
- price movement outside resource-family thresholds;
- stale but not expired observation;
- single-source observation;
- description similarity without specification equivalence;
- geography broader than the target project;
- missing freight or minimum-order terms;
- converted unit requiring rounding; or
- manual override from the organization baseline.

Warnings never disappear. Publication records who accepted each warning and why.

### 9.3 Confidence grades

- **A — Verified:** at least three recent comparable market observations plus an
  official or licensed reference cross-check.
- **B — Supported:** two independent comparable observations, or an approved
  licensed catalog corroborated by a current index/reference.
- **C — Reference:** one identifiable source with complete metadata.
- **Seed:** incomplete provenance, date, geography, or cost basis.
- **Rejected:** blocking domain or rights failure.

Grades are computed from evidence and policy; users cannot directly type `A`.

Draft and sandbox estimates may use Seed inputs when the user explicitly selects
prototype mode; every affected line and total is marked untrusted. Seed inputs
cannot appear in any issued estimate.

For every issued estimate:

- no Seed, Rejected, expired, or unresolved price is allowed;
- every line has a traceable source and effective date; and
- every accepted C-grade input records an exception reason.

For a controlled issued estimate, the additional default policy is:

- at least 95% of direct cost uses A or B inputs;
- any C-grade line contributing at least 1% of direct cost requires an explicit
  exception approved by the second approver.

Organizations may impose stricter rules but cannot weaken platform invariants.

## 10. Deterministic Price Resolution

The resolver accepts:

- organization and project;
- concept/APU or resource;
- required unit and quantity;
- project geography and valuation date;
- requested cost basis; and
- budget control policy.

Precedence is:

1. approved, unexpired project supplier quotation;
2. approved project override;
3. active organization price-book version;
4. active Klave CDMX price-book version;
5. active Klave state price-book version;
6. unresolved.

The resolver:

- rejects incompatible units and cost bases;
- converts only through approved conversions;
- applies no IVA, indirect, financing, or profit factor unless the caller
  requests an approved financial profile;
- returns the selected observation, alternatives considered, conversions,
  confidence, warnings, and reason;
- never returns zero as a missing-price substitute.

A budget stores a resolution snapshot. Later catalog changes do not modify an
existing draft revision or issued budget.

## 11. CDMX Trusted Baseline Program

### 11.1 Source layers

1. **Current seed corpus**
   - import with `Seed` confidence;
   - preserve unknown dates and geography as explicit unknowns;
   - use data-quality failures as regression cases.
2. **Official anchors**
   - monthly CDMX Tabulador General and notes;
   - INEGI construction/material indices;
   - PROFECO construction-material observations;
   - annual CONASAMI and IMSS labor guardrails.
3. **Licensed professional references**
   - CMIC/CEICO only after a license permits the intended product use.
4. **Direct market observations**
   - recurring supplier, ready-mix, steel, block, equipment, transport, and
     disposal quotations.
5. **Consented customer actuals**
   - tenant-private quotations, purchase orders, invoices, production records,
     change orders, and final accounts.

Public or visible data is not automatically licensed for redistribution. Every
source receives a rights classification before use in a platform book.

### 11.2 First baseline basket

The first trusted CDMX release targets:

- 80–120 high-impact resources;
- 15–25 representative crew definitions;
- 60–100 structural and obra-negra APUs; and
- measurement-compatible concepts for earthwork, foundations, concrete,
  reinforcement, formwork, columns/castillos, beams/dalas, slabs, masonry, and
  rough drainage.

This basket is selected by expected spend and drawing detectability. Klave does
not attempt to validate all 2,698 seed concepts before shipping useful results.

### 11.3 Refresh cadence

Cadence is a policy per resource family and source, not one global interval.

- Official CDMX and INEGI sources are checked monthly.
- Volatile high-impact materials are refreshed at least monthly.
- Supplier quotation expiration is honored exactly.
- Labor and equipment are reviewed at least quarterly and after material market
  changes.
- Every publication is a proposed version with diff and approval, never an
  in-place automatic update.

### 11.4 Geography

The initial platform book is CDMX-wide. Alcaldía or market-zone factors are
published only after sufficient comparable observations exist.

Access, working-hour restrictions, building height, pumping distance, soil,
haul distance, disposal site, storage, and neighborhood logistics are project
conditions, not hidden geographic multipliers.

Other Mexican markets begin with a state-level book plus explicit observations
and project modifiers. CDMX standardizes the data model and process, not every
regional price.

## 12. API Surface

The initial API exposes:

- source-document upload and metadata;
- import-batch creation and status;
- schema/template detection;
- mapping configuration;
- validation findings and staged-row correction;
- version diff;
- catalog publication and version listing;
- concepts, resources, crews, rendimientos, and APUs;
- price observations and price-book entries;
- deterministic price resolution;
- approval actions; and
- audit/provenance lookup.

All list endpoints are paginated and tenant-scoped. Mutating endpoints require
idempotency keys. Published versions use optimistic concurrency checks so two
reviewers cannot publish competing drafts accidentally.

## 13. User Experience

The catalog workspace contains:

1. **Sources:** uploaded files, official feeds, rights, dates, and status.
2. **Imports:** mapping wizard, validation findings, quarantine, and retry.
3. **Catalogs:** draft and published versions with diffs.
4. **APUs:** component tree, resource prices, rendimiento, and recomputed cost.
5. **Price evidence:** selected observation and alternatives.
6. **Approvals:** ordinary and controlled workflows.

Every displayed price provides a provenance drawer. Every manual correction
requires a reason. Users can export the normalized data and the validation report
to Excel/CSV.

## 14. Error Handling and Audit

- Import jobs are restartable and idempotent by source hash plus mapping version.
- Partial parsing never publishes partial catalog state.
- Quarantined rows remain attached to their source and import batch.
- Domain errors use stable machine-readable codes and Spanish messages.
- Unexpected failures record a correlation ID without exposing another tenant's
  data.
- Audit events are append-only for upload, mapping, correction, validation,
  publication, retirement, override, approval, and export.
- Published catalog versions and issued budget snapshots cannot be edited or
  deleted through ordinary product operations.

## 15. Security and Data Lifecycle

- Raw uploads are private and encrypted at rest in production.
- File downloads require authorization and short-lived links.
- Formula and macro execution is disabled.
- CSV export is protected against formula injection.
- Uploaded files pass through a `FileScanner` adapter before parsing. Hosted
  deployments fail closed when the scanner is unavailable; the no-op adapter is
  restricted to explicit local-development mode.
- Tenant data is excluded from training or cross-tenant benchmarks unless the
  organization explicitly opts in under a documented agreement.
- Organization deletion uses a documented retention and recoverability process;
  it is not implemented as an unscoped cascade.
- Secrets and connection strings are never stored in catalog metadata or source
  documents.

## 16. Integration With the Current Engine

The existing hard-coded seven-concept catalog remains behind an adapter during
migration.

The new price resolver implements the same narrow interface first, allowing
current cost-plan generation to switch through a feature flag. Once parity is
verified:

1. seed concepts map to canonical concept UUIDs;
2. current defaults become an explicitly versioned, reference-only Seed price
   book;
3. the engine receives resolved-price evidence rather than naked numeric prices;
4. missing or incompatible prices become blocking findings; and
5. the hard-coded catalog is removed only after regression and rollback coverage
   exists.

Until a publishable CDMX book exists, the feature flag permits the legacy Seed
book only for draft/prototype budgets. It cannot issue or approve a budget.

Drawing JSON artifacts remain immutable. New runs record the catalog version,
APU version, price-resolution policy, and financial profile used.

## 17. Testing Strategy

### 17.1 Unit tests

- unit aliases and dimensional conversions;
- Decimal parsing and rounding;
- tax and cost-basis handling;
- duplicate/equivalence rules;
- APU arithmetic and cycle rejection;
- confidence grading;
- price precedence and expiration;
- controlled-approval separation.

### 17.2 Import contract tests

- Klave templates;
- representative Centro, Sur, Norte, rendimiento, composite-price, and broken
  quantity schemas;
- formula errors and external links;
- Unicode accents and decomposed filenames;
- duplicate codes;
- `kg`/`t` valid conversions;
- CSV formula injection;
- idempotent re-import and diff behavior.

Raw supplied workbooks are not committed without confirmed rights. Tests use
minimal redacted fixtures that preserve schema and failure characteristics.

### 17.3 Integration tests

- database migrations from empty and prior schema;
- tenant row-level-security isolation;
- upload through publication;
- concurrent reviewer conflict;
- source-to-budget provenance;
- immutable published versions;
- resolver behavior across project, organization, CDMX, and state layers.

### 17.4 End-to-end acceptance

- Import a documented Excel template.
- Correct quarantined rows.
- Publish an organization catalog.
- Resolve a project quote over the organization and platform books.
- Produce a budget revision with a complete price-evidence chain.
- Verify ordinary self-approval.
- Verify controlled self-approval is rejected and second-person approval works.

## 18. Rollout

### Milestone 1: Domain and persistence

- PostgreSQL, migrations, tenant model, catalog domain, units, sources, and
  immutable versions.

### Milestone 2: Excel/CSV ingestion

- raw uploads, supported templates, mapping, normalization, validation,
  quarantine, diff, and publication.

### Milestone 3: Seed migration

- import current workbooks as Seed;
- establish regression fixtures;
- map the existing seven concepts through the resolver adapter.

### Milestone 4: CDMX baseline

- official source ingestion;
- first high-impact resource basket;
- supplier quote template;
- first 60–100 approved structural/obra-negra APUs.

### Milestone 5: Product workflow

- catalog UI, provenance, approvals, export, and controlled-estimate policy.

### Milestone 6: Calibration

- validate against at least three representative CDMX projects;
- compare estimate versus professional budget and available actuals;
- adjust mappings, APUs, and validation thresholds through versioned changes.

## 19. Success Criteria

The project is complete when:

- every tenant-owned record is isolated and covered by cross-tenant tests;
- all six source schemas can be represented through the import pipeline, with
  invalid rows quarantined deterministically;
- no published price lacks source, unit, geography, effective date, currency,
  tax basis, and cost basis;
- every published catalog is immutable and reproducible;
- price resolution follows the approved precedence and never silently returns
  zero;
- controlled estimates enforce second-person approval;
- the existing cost-plan path can consume versioned resolver results;
- a first CDMX basket of 60–100 structural/obra-negra APUs is published with
  explicit confidence;
- at least three representative CDMX projects complete calibration review; and
- product documentation explains how users import, validate, approve, and audit
  catalogs.

## 20. Follow-On Design Gates

This specification deliberately does not authorize implementation of the
geometry or financial-engine redesign. After this platform is planned, the next
design must define:

- canonical drawing units and coordinate frames;
- scale/unit hard gates;
- element hypotheses versus accepted elements;
- evidence-backed user corrections;
- quantity and waste rules;
- structural and obra-negra measurement coverage;
- schedule productivity linkage;
- indirect, financing, utility, tax, escalation, and cash-flow profiles; and
- issued-budget revision controls.
