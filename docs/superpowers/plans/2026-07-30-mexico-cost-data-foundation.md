# Mexico Cost Data Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a working backend vertical slice for tenant-safe Excel/CSV cost-data ingestion, validation, immutable catalog publication, deterministic price resolution, and evidence-bearing integration with Klave's existing costing engine.

**Architecture:** Add a `cost_data` bounded context to the existing Python modular monolith. PostgreSQL is the shared system of record; raw files use an object-store abstraction; imports are claimed by a PostgreSQL-backed worker; FastAPI exposes tenant-scoped workflows; the existing costing package consumes a narrow price-provider interface while its hard-coded data remains a reference-only prototype fallback.

**Tech Stack:** Python 3.11+, Pydantic 2, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16, psycopg 3, PyJWT, openpyxl, pytest, Ruff, mypy, Docker Compose

## Global Constraints

- Mexico and MXN are first-class; CDMX is the first platform region.
- The product is multi-tenant; every tenant-owned database row carries `organization_id`.
- Hosted authentication verifies a configured OIDC JWT; local identity overrides are impossible outside explicit development mode.
- PostgreSQL row-level security is required in addition to repository-level tenant filtering.
- Money and coefficients use `Decimal`; financial boundaries do not accept floating-point input.
- V1 accepts `.xlsx` and UTF-8 `.csv`; it rejects `.xls`, `.xlsm`, password-protected files, macros, and executable content.
- Raw source values, sheet names, row numbers, formulas, and file SHA-256 remain immutable evidence.
- Published catalog versions are immutable.
- Seed data is reference-only. It may power explicitly marked draft/prototype budgets but cannot issue or approve a budget.
- Missing prices resolve as `unresolved`; zero is never a fallback.
- Project quote precedence is: approved project quote, approved project override, organization book, Klave CDMX book, Klave state book, unresolved.
- OPUS, Neodata, the catalog UI, live official-source connectors, and baseline market calibration are outside this first plan.
- All implementation tasks follow red-green-refactor TDD and end with a focused commit.

---

## Target File Structure

```text
packages/klave_engine/
  cost_data/
    __init__.py                 Public cost-data exports
    enums.py                    Stable domain enums
    values.py                   Decimal money and quantity value objects
    units.py                    Canonical unit registry and conversions
    findings.py                 Stable validation finding contract
    schemas.py                  API/domain command and result models
    validation.py               Row and cross-row validation rules
    confidence.py               Evidence-derived confidence grading
    pricing.py                  Deterministic price resolver
    approvals.py                Catalog and estimate approval invariants
    storage.py                  Object-store and file-scanner ports/adapters
    imports/
      __init__.py
      contracts.py              Parser-neutral workbook representation
      csv_parser.py             UTF-8 CSV parser
      xlsx_parser.py            Safe XLSX parser
      mapping.py                Mapping specification and normalization
      service.py                Import orchestration
    persistence/
      __init__.py
      base.py                   SQLAlchemy base and naming convention
      session.py                Engine/session and tenant transaction context
      tenancy.py                Organization, user, membership, project access
      catalog.py                Catalog, version, concepts, resources, APUs
      imports.py                Sources, batches, staged rows, import jobs
      pricing.py                Observations, books, entries, approvals, audit
      repositories.py           Tenant-aware repositories
  costing/
    price_provider.py           Compatibility port into existing costing

apps/
  api/
    auth.py                     OIDC and development identity dependency
    database.py                 Request-scoped database session
    idempotency.py              Mutation idempotency guard
    routes/
      catalog_imports.py
      catalogs.py
      price_books.py
  worker/
    __init__.py
    main.py                     PostgreSQL import worker

alembic.ini
migrations/
  env.py
  versions/
compose.yaml
tests/
  cost_data/
  integration/
```

The second implementation plan will add the Next.js catalog workspace, official
CDMX/INEGI/PROFECO connectors, supplier quote operations, and baseline
calibration.

---

### Task 1: Decimal Value Objects and Canonical Unit Registry

**Files:**
- Create: `packages/klave_engine/cost_data/__init__.py`
- Create: `packages/klave_engine/cost_data/enums.py`
- Create: `packages/klave_engine/cost_data/values.py`
- Create: `packages/klave_engine/cost_data/units.py`
- Create: `packages/klave_engine/cost_data/findings.py`
- Test: `tests/cost_data/test_values_and_units.py`

**Interfaces:**
- Produces: `parse_decimal(value: object) -> Decimal`
- Produces: `Money(amount: Decimal, currency: Literal["MXN"])`
- Produces: `Quantity(value: Decimal, unit_code: str)`
- Produces: `UnitRegistry.normalize(alias: str) -> UnitDefinition`
- Produces: `UnitRegistry.convert(value: Decimal, source: str, target: str) -> Decimal`
- Produces: `ValidationFinding(code, severity, message, source_locator, context)`

- [ ] **Step 1: Write failing tests for Decimal rejection and unit conversion**

```python
# tests/cost_data/test_values_and_units.py
from decimal import Decimal

import pytest
from pydantic import ValidationError

from klave_engine.cost_data.units import DEFAULT_UNITS, UnitConversionError
from klave_engine.cost_data.values import Money, Quantity, parse_decimal


def test_parse_decimal_rejects_float_and_non_finite_values() -> None:
    with pytest.raises(TypeError, match="float"):
        parse_decimal(12.3)
    with pytest.raises(ValueError, match="finite"):
        parse_decimal("NaN")


def test_money_is_mxn_and_non_negative() -> None:
    assert Money(amount="123.4500").amount == Decimal("123.4500")
    with pytest.raises(ValidationError):
        Money(amount="-0.01")


def test_unit_aliases_and_mass_conversion() -> None:
    assert DEFAULT_UNITS.normalize("M²").code == "m2"
    assert DEFAULT_UNITS.normalize("TON").code == "t"
    assert DEFAULT_UNITS.convert(Decimal("2.5"), "t", "kg") == Decimal("2500.0")


def test_incompatible_units_never_convert() -> None:
    with pytest.raises(UnitConversionError, match="mass.*area"):
        DEFAULT_UNITS.convert(Decimal("1"), "kg", "m2")


def test_quantity_normalizes_alias_without_losing_decimal() -> None:
    quantity = Quantity(value="1.250", unit_code="M3")
    assert quantity.value == Decimal("1.250")
    assert quantity.unit_code == "m3"
```

- [ ] **Step 2: Run the focused tests and verify the import failure**

Run: `.venv/bin/pytest tests/cost_data/test_values_and_units.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'klave_engine.cost_data'`.

- [ ] **Step 3: Implement stable enums, values, findings, and the initial unit registry**

```python
# packages/klave_engine/cost_data/enums.py
from enum import StrEnum


class OwnershipScope(StrEnum):
    PLATFORM = "platform"
    ORGANIZATION = "organization"
    PROJECT = "project"


class CatalogStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    PUBLISHED = "published"
    SUPERSEDED = "superseded"


class ConfidenceGrade(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    SEED = "Seed"
    REJECTED = "Rejected"


class FindingSeverity(StrEnum):
    BLOCKING = "blocking"
    WARNING = "warning"
    INFORMATIONAL = "informational"


class CostBasis(StrEnum):
    DIRECT = "direct"
    INTEGRATED = "integrated"


class ResourceKind(StrEnum):
    LABOR = "labor"
    MATERIAL = "material"
    EQUIPMENT = "equipment"
    SUBCONTRACT = "subcontract"
    TOOL = "tool"
    AUXILIARY = "auxiliary"
    WASTE = "waste"


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    ESTIMATOR = "estimator"
    APPROVER = "approver"
    VIEWER = "viewer"


class UsageRights(StrEnum):
    UNKNOWN = "unknown"
    INTERNAL_ONLY = "internal_only"
    DERIVED_USE = "derived_use"
    REDISTRIBUTION = "redistribution"
```

```python
# packages/klave_engine/cost_data/values.py
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


def parse_decimal(value: object) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError("financial values cannot be bool or float")
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError("invalid decimal value") from exc
    if not parsed.is_finite():
        raise ValueError("decimal value must be finite")
    return parsed


class Money(BaseModel):
    model_config = ConfigDict(frozen=True)
    amount: Decimal
    currency: Literal["MXN"] = "MXN"

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, value: object) -> Decimal:
        parsed = parse_decimal(value)
        if parsed < 0:
            raise ValueError("money cannot be negative")
        return parsed


class Quantity(BaseModel):
    model_config = ConfigDict(frozen=True)
    value: Decimal
    unit_code: str

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, value: object) -> object:
        from klave_engine.cost_data.units import DEFAULT_UNITS

        data = dict(value) if isinstance(value, dict) else value
        if isinstance(data, dict):
            data["value"] = parse_decimal(data["value"])
            data["unit_code"] = DEFAULT_UNITS.normalize(str(data["unit_code"])).code
        return data
```

Implement `UnitDefinition`, `UnitRegistry`, and `UnitConversionError` in
`units.py`. Register `m`, `m2`, `m3`, `kg`, `t`, `piece`, `hour`, `crew_day`,
`service`, `lot`, `outlet`, `trip`, and `pct_labor`; include aliases observed in
the supplied workbooks (`M`, `ML`, `M2`, `M²`, `M3`, `M³`, `KG`, `TON`, `PZA`,
`HR`, `JOR`, `SAL`, `SALIDA`, `VIAJE`, `(%)MO`, `%MO`). Only units sharing the
same `dimension` and a context-free factor may convert.

Implement `ValidationFinding` in `findings.py` as a frozen Pydantic model using
`FindingSeverity`.

- [ ] **Step 4: Run unit tests and static checks**

Run: `.venv/bin/pytest tests/cost_data/test_values_and_units.py -q`

Expected: PASS.

Run: `.venv/bin/ruff check packages/klave_engine/cost_data tests/cost_data`

Expected: exit 0.

- [ ] **Step 5: Commit the domain primitives**

```bash
git add packages/klave_engine/cost_data tests/cost_data/test_values_and_units.py
git commit -m "feat: add cost data value objects and units"
```

---

### Task 2: PostgreSQL, Migrations, and Tenant Transaction Context

**Files:**
- Modify: `pyproject.toml:1-23`
- Modify: `packages/klave_engine/common/config.py:1-31`
- Create: `packages/klave_engine/cost_data/persistence/__init__.py`
- Create: `packages/klave_engine/cost_data/persistence/base.py`
- Create: `packages/klave_engine/cost_data/persistence/session.py`
- Create: `packages/klave_engine/cost_data/persistence/tenancy.py`
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/script.py.mako`
- Create: `migrations/versions/20260730_0001_tenancy.py`
- Create: `compose.yaml`
- Test: `tests/cost_data/test_settings.py`
- Test: `tests/integration/test_tenant_isolation.py`

**Interfaces:**
- Consumes: `Role`
- Produces: `Base`
- Produces: `create_session_factory(database_url: str) -> sessionmaker[Session]`
- Produces: `tenant_transaction(factory, context) -> Iterator[Session]`
- Produces: `TenantContext(organization_id, user_id, roles)`
- Produces tables: `organizations`, `users`, `memberships`, `project_access`

- [ ] **Step 1: Write failing configuration and PostgreSQL isolation tests**

```python
# tests/cost_data/test_settings.py
import pytest
from pydantic import ValidationError

from klave_engine.common.config import Settings


def test_hosted_mode_requires_database_and_oidc() -> None:
    with pytest.raises(ValidationError, match="database_url"):
        Settings(environment="hosted")


def test_dev_identity_is_rejected_in_hosted_mode() -> None:
    with pytest.raises(ValidationError, match="development identity"):
        Settings(
            environment="hosted",
            database_url="postgresql+psycopg://u:p@db/klave",
            oidc_issuer="https://issuer.example",
            oidc_audience="klave",
            oidc_jwks_url="https://issuer.example/.well-known/jwks.json",
            dev_organization_id="11111111-1111-1111-1111-111111111111",
        )
```

```python
# tests/integration/test_tenant_isolation.py
def test_rls_hides_another_organizations_project(postgres_factory, seeded_tenants) -> None:
    org_a, user_a, org_b, project_b = seeded_tenants
    context = TenantContext(organization_id=org_a, user_id=user_a, roles={Role.ADMIN})
    with tenant_transaction(postgres_factory, context) as session:
        assert session.get(ProjectAccess, project_b) is None
```

- [ ] **Step 2: Run tests and verify missing settings/database modules**

Run: `.venv/bin/pytest tests/cost_data/test_settings.py -q`

Expected: FAIL because the hosted settings and validators do not exist.

Run with PostgreSQL from `KLAVE_TEST_DATABASE_URL`:

```bash
docker compose up -d postgres
KLAVE_TEST_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave_test \
  .venv/bin/pytest tests/integration/test_tenant_isolation.py -q
```

Expected: FAIL because persistence models do not exist.

- [ ] **Step 3: Add dependencies and validated settings**

Add these runtime dependencies to `pyproject.toml` and refresh `uv.lock`:

```toml
"sqlalchemy>=2.0.36",
"alembic>=1.14",
"psycopg[binary]>=3.2",
"PyJWT[crypto]>=2.10",
"openpyxl>=3.1.5",
"boto3>=1.35",
"clamd>=1.0.2",
```

Add settings fields:

```python
environment: Literal["development", "test", "hosted"] = "development"
database_url: str | None = None
worker_database_url: str | None = None
oidc_issuer: str | None = None
oidc_audience: str | None = None
oidc_jwks_url: str | None = None
dev_organization_id: UUID | None = None
dev_user_id: UUID | None = None
source_storage_dir: Path = Path("data/source_documents")
source_storage_backend: Literal["local", "s3"] = "local"
s3_bucket: str | None = None
s3_endpoint_url: str | None = None
clamav_host: str | None = None
clamav_port: int = 3310
max_catalog_upload_bytes: int = 25 * 1024 * 1024
```

Add an `after` model validator: hosted mode requires the application database,
worker database, and all OIDC fields, `source_storage_backend="s3"`, an S3
bucket, and a ClamAV host; it rejects either development identity field.

- [ ] **Step 4: Implement the SQLAlchemy base, tenant models, transaction context, and migration**

Use a deterministic metadata naming convention in `base.py`. Define UUID primary
keys and UTC timestamps in `tenancy.py`:

```python
class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    oidc_subject: Mapped[str] = mapped_column(String(255), unique=True)


class Membership(Base):
    __tablename__ = "memberships"
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    roles: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)


class ProjectAccess(Base):
    __tablename__ = "project_access"
    project_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id"), nullable=False, index=True
    )
```

`tenant_transaction` must call:

```python
session.execute(
    text("SET LOCAL klave.organization_id = :organization_id"),
    {"organization_id": str(context.organization_id)},
)
```

The migration creates roles, tables, indexes, enables and forces RLS on
`project_access`, and creates a policy comparing `organization_id` with
`current_setting('klave.organization_id', true)::uuid`.

`compose.yaml` runs PostgreSQL 16 with a health check and initializes:

- `klave_owner`, which owns schemas and runs Alembic;
- `klave_app`, which does not own tables and is subject to RLS;
- `klave_worker`, which has `BYPASSRLS` and is used only by the import worker;
- `klave` and `klave_test` databases.

API and integration-test URLs use `klave_app`; migration URLs use
`klave_owner`. The worker credential is never available to the API process.

- [ ] **Step 5: Apply migrations and prove tenant isolation**

Run:

```bash
uv lock
uv sync --all-groups
docker compose up -d postgres
KLAVE_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave \
  .venv/bin/alembic upgrade head
KLAVE_TEST_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave_test \
  .venv/bin/pytest tests/cost_data/test_settings.py tests/integration/test_tenant_isolation.py -q
```

Expected: migrations succeed and all tests pass.

- [ ] **Step 6: Commit persistence and tenancy**

```bash
git add pyproject.toml uv.lock packages/klave_engine/common/config.py \
  packages/klave_engine/cost_data/persistence alembic.ini migrations compose.yaml \
  tests/cost_data/test_settings.py tests/integration/test_tenant_isolation.py
git commit -m "feat: add tenant-safe PostgreSQL foundation"
```

---

### Task 3: Catalog, APU, Import, Pricing, and Audit Persistence

**Files:**
- Create: `packages/klave_engine/cost_data/persistence/catalog.py`
- Create: `packages/klave_engine/cost_data/persistence/imports.py`
- Create: `packages/klave_engine/cost_data/persistence/pricing.py`
- Create: `packages/klave_engine/cost_data/persistence/repositories.py`
- Create: `migrations/versions/20260730_0002_cost_data.py`
- Test: `tests/integration/test_catalog_persistence.py`

**Interfaces:**
- Consumes: `Base`, `CatalogStatus`, `ConfidenceGrade`, `OwnershipScope`
- Produces: `CatalogRepository`
- Produces: `ImportRepository`
- Produces: `PricingRepository`
- Produces: immutable catalog and price-book version records

- [ ] **Step 1: Write failing lifecycle and tenant-uniqueness tests**

```python
def test_published_catalog_version_cannot_be_updated(tenant_session) -> None:
    version = catalog_factory(status=CatalogStatus.PUBLISHED)
    tenant_session.add(version)
    tenant_session.commit()
    version.label = "changed"
    with pytest.raises(IntegrityError, match="published"):
        tenant_session.commit()


def test_source_alias_is_unique_only_inside_organization_and_version(
    session_for_org_a, session_for_org_b
) -> None:
    create_alias(session_for_org_a, source_code="CIM-001")
    create_alias(session_for_org_b, source_code="CIM-001")
    session_for_org_a.commit()
    session_for_org_b.commit()


def test_price_observation_requires_explicit_tax_and_cost_basis(tenant_session) -> None:
    with pytest.raises(IntegrityError):
        tenant_session.add(price_observation(iva_included=None, cost_basis=None))
        tenant_session.commit()
```

- [ ] **Step 2: Run the migration test and verify missing models**

Run:

```bash
KLAVE_TEST_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave_test \
  .venv/bin/pytest tests/integration/test_catalog_persistence.py -q
```

Expected: FAIL on missing persistence classes.

- [ ] **Step 3: Implement focused persistence modules**

Create these tables with UUID primary keys, UTC timestamps, foreign keys, and
tenant-aware indexes:

```text
catalog.py:
  regions
  unit_aliases
  catalogs
  catalog_versions
  work_categories
  concepts
  concept_aliases
  resources
  crews
  crew_members
  rendimientos
  apus
  apu_components
  concept_mappings

imports.py:
  source_documents
  import_batches
  staged_rows
  import_jobs

pricing.py:
  price_observations
  price_books
  price_book_versions
  price_book_entries
  approvals
  audit_events
  idempotency_records
```

Use these required field groups:

```text
regions:
  id, country_code, state_code, market_code, name, parent_id

unit_aliases:
  id, organization_id, raw_alias, canonical_unit_code, approved_by, approved_at

catalogs:
  id, organization_id, project_id, ownership_scope, name, reference_only

catalog_versions:
  id, organization_id, catalog_id, status, label, base_version_id,
  effective_from, effective_to, validation_summary, approved_by, approved_at,
  published_by, published_at

work_categories:
  id, organization_id, catalog_version_id, parent_id, code, name, sort_order

concepts:
  id, organization_id, catalog_version_id, stable_key, description,
  default_unit_code, category_id, specification_json, active

concept_aliases:
  id, organization_id, catalog_version_id, concept_id, source_system,
  source_code, source_description, source_locator

resources:
  id, organization_id, catalog_version_id, stable_key, resource_kind,
  description, purchasing_unit_code, specification_json, active

crews / crew_members:
  crew stable_key, description, output unit; member labor_resource_id and
  Decimal quantity

rendimientos:
  id, organization_id, catalog_version_id, concept_id, crew_id,
  Decimal output_per_crew_day, output_unit_code, conditions_json,
  source_document_id, source_locator, confidence_grade, effective_from,
  effective_to

apus / apu_components:
  APU concept_id, output_unit_code, Decimal output_quantity, region_id,
  effective dates, status, source and version; component resource_id,
  nested_apu_id, Decimal coefficient, Decimal waste_factor, unit_code,
  percentage_base

concept_mappings:
  id, organization_id, catalog_version_id, assembly_family,
  measurement_rule_ref, specification_predicates_json, concept_id, priority

source_documents:
  id, organization_id, storage_key, original_filename, media_type, byte_size,
  sha256, source_organization, source_url, usage_rights, asserted_region_id,
  asserted_effective_date, uploaded_by, uploaded_at

import_batches / staged_rows / import_jobs:
  tenant and source IDs, parser/mapping/rule versions, mapping JSON/hash,
  status/counts/reviewer/publisher; exact sheet/row locator, raw JSON,
  normalized JSON, findings JSON, disposition; durable claim/attempt/error data

price_observations:
  id, organization_id, resource_id, concept_id, Decimal amount, currency,
  original_unit_code, canonical_unit_code, region_id, observed_at,
  effective_from, expires_at, iva_included, tax_profile_code, cost_basis,
  freight_terms, delivery_terms, pumping_terms, minimum_order,
  payment_terms, source_document_id, source_locator, confidence_grade,
  approval_status

price_books / price_book_versions / price_book_entries:
  ownership and region, cost basis, immutable lifecycle/effective dates,
  selected observation or computed APU, selection reason, approver

approvals / audit_events / idempotency_records:
  actor, subject, action, reason, before/after JSON, timestamps; route/key,
  request hash, response status/body
```

`PLATFORM_ORGANIZATION_ID` is a documented fixed UUID inserted by migration.
Platform rows use that owner and `ownership_scope="platform"`. RLS permits rows
owned by the current organization plus published platform rows; platform writes
remain restricted to the platform-admin service role.

Required invariants:

```python
CheckConstraint("amount > 0", name="price_observation_amount_positive")
CheckConstraint(
    "(resource_id IS NOT NULL) <> (concept_id IS NOT NULL)",
    name="price_observation_one_subject",
)
CheckConstraint("rendimiento > 0", name="rendimiento_positive")
UniqueConstraint(
    "organization_id", "catalog_version_id", "source_system", "source_code",
    name="uq_concept_alias_source_code",
)
UniqueConstraint(
    "organization_id", "source_document_id", "mapping_hash",
    name="uq_import_batch_idempotent",
)
```

Catalog and price-book rows use platform, organization, or project scope with a
check constraint that requires the matching owner identifiers. `StagedRow`
stores `raw_payload`, `normalized_payload`, and `findings` as JSONB plus
`sheet_name`, `row_number`, and `disposition`.

Create PostgreSQL triggers that reject UPDATE and DELETE for published
`catalog_versions`, published `price_book_versions`, and their child entries.
Enable and force RLS on every table carrying `organization_id`.

- [ ] **Step 4: Implement repositories that always require `TenantContext`**

Repository constructors accept `Session` and `TenantContext`. Do not expose an
unscoped `list_all`.

```python
class CatalogRepository:
    def __init__(self, session: Session, tenant: TenantContext) -> None: ...
    def get_version(self, version_id: UUID) -> CatalogVersion | None: ...
    def add_draft(self, command: CreateCatalogDraft) -> CatalogVersion: ...
    def list_versions(self, catalog_id: UUID, *, limit: int, offset: int) -> list[CatalogVersion]: ...


class ImportRepository:
    def find_idempotent_batch(self, source_id: UUID, mapping_hash: str) -> ImportBatch | None: ...
    def add_staged_rows(self, batch_id: UUID, rows: Sequence[StagedRowInput]) -> None: ...
    def claim_next_job(self, worker_id: str) -> ImportJob | None: ...


class PricingRepository:
    def candidate_observations(self, request: PriceResolutionRequest) -> list[PriceObservation]: ...
    def add_audit_event(self, event: AuditEventInput) -> None: ...
```

`claim_next_job` uses `SELECT ... FOR UPDATE SKIP LOCKED`.

- [ ] **Step 5: Apply migration and run persistence tests**

Run:

```bash
KLAVE_TEST_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave_test \
  .venv/bin/alembic upgrade head
KLAVE_TEST_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave_test \
  .venv/bin/pytest tests/integration/test_catalog_persistence.py -q
```

Expected: PASS, including immutable-trigger and RLS assertions.

- [ ] **Step 6: Commit the cost-data schema**

```bash
git add packages/klave_engine/cost_data/persistence \
  migrations/versions/20260730_0002_cost_data.py \
  tests/integration/test_catalog_persistence.py
git commit -m "feat: persist versioned catalogs and prices"
```

---

### Task 4: Immutable Source Storage and Safe CSV/XLSX Parsing

**Files:**
- Create: `packages/klave_engine/cost_data/storage.py`
- Create: `packages/klave_engine/cost_data/imports/__init__.py`
- Create: `packages/klave_engine/cost_data/imports/contracts.py`
- Create: `packages/klave_engine/cost_data/imports/csv_parser.py`
- Create: `packages/klave_engine/cost_data/imports/xlsx_parser.py`
- Create: `tests/cost_data/fixtures/catalog.csv`
- Create: `tests/cost_data/test_storage.py`
- Create: `tests/cost_data/test_parsers.py`

**Interfaces:**
- Produces: `ObjectStore.put(stream, *, sha256, suffix) -> StoredObject`
- Produces: `FileScanner.scan(path) -> ScanResult`
- Produces: `CatalogParser.parse(path) -> ParsedWorkbook`
- Produces: `parser_for(path: Path) -> CatalogParser`
- Produces: `ParsedCell(raw_value, displayed_value, formula, locator)`

- [ ] **Step 1: Write failing parser and immutable-storage tests**

```python
def test_csv_parser_preserves_locator_and_utf8(tmp_path) -> None:
    path = tmp_path / "catálogo.csv"
    path.write_text("CLAVE,DESCRIPCIÓN,UNIDAD,PRECIO\nCIM-1,Concreto,M3,2650.50\n", "utf-8")
    workbook = CsvCatalogParser().parse(path)
    cell = workbook.sheets[0].rows[1].cells[3]
    assert cell.raw_value == "2650.50"
    assert cell.locator == "catalog.csv!D2"


def test_xlsx_parser_preserves_formula_and_flags_missing_cached_value(xlsx_fixture) -> None:
    workbook = XlsxCatalogParser().parse(xlsx_fixture)
    total = workbook.sheets[0].rows[1].cells[5]
    assert total.formula == "=D2*E2"
    assert total.locator.endswith("!F2")
    assert total.displayed_value is None
    assert "formula_cached_value_missing" in {w.code for w in workbook.warnings}


@pytest.mark.parametrize("name", ["catalog.xls", "catalog.xlsm"])
def test_unsupported_excel_types_are_rejected(tmp_path, name) -> None:
    path = tmp_path / name
    path.write_bytes(b"not executable")
    with pytest.raises(UnsupportedCatalogFile):
        parser_for(path)


def test_local_object_store_is_content_addressed_and_immutable(tmp_path) -> None:
    store = LocalObjectStore(tmp_path)
    first = store.put(io.BytesIO(b"abc"), sha256=hashlib.sha256(b"abc").hexdigest(), suffix=".csv")
    second = store.put(io.BytesIO(b"abc"), sha256=first.sha256, suffix=".csv")
    assert first.key == second.key
    assert store.open(first.key).read() == b"abc"


def test_hosted_scanner_fails_closed_when_clamav_is_unavailable() -> None:
    scanner = ClamAvScanner(host="127.0.0.1", port=65534)
    with pytest.raises(FileScanUnavailable):
        scanner.scan(Path("tests/cost_data/fixtures/catalog.csv"))
```

- [ ] **Step 2: Run parser tests and confirm they fail**

Run: `.venv/bin/pytest tests/cost_data/test_storage.py tests/cost_data/test_parsers.py -q`

Expected: FAIL because storage and parser contracts do not exist.

- [ ] **Step 3: Implement storage and scanner ports**

```python
class ObjectStore(Protocol):
    def put(self, stream: BinaryIO, *, sha256: str, suffix: str) -> StoredObject: ...
    def open(self, key: str) -> BinaryIO: ...


class FileScanner(Protocol):
    def scan(self, path: Path) -> ScanResult: ...


class DevelopmentNoopScanner:
    def __init__(self, environment: str) -> None:
        if environment not in {"development", "test"}:
            raise RuntimeError("no-op scanner is forbidden in hosted mode")
```

`LocalObjectStore` writes to `<root>/<sha256[:2]>/<sha256><suffix>` using a
temporary file and atomic rename. If the content-addressed object already
exists, verify its hash and reuse it without mutation.

Implement `S3ObjectStore` with private objects, server-side encryption, and keys
`sha256[:2]/sha256+suffix`. Use a configured bucket and optional S3-compatible
endpoint; never set a public ACL. Unit tests use `botocore.stub.Stubber` and
assert the encryption and bucket/key arguments.

Implement `ClamAvScanner` with the `clamd` TCP adapter. `OK` passes, `FOUND`
raises `UnsafeCatalogFile`, and connection/protocol failure raises
`FileScanUnavailable`. Hosted upload handling returns 503 on scanner
unavailability and never stores or parses the file.

- [ ] **Step 4: Implement parser-neutral contracts and safe parsers**

`ParsedWorkbook` contains workbook metadata and ordered `ParsedSheet` objects.
Each cell retains raw value, displayed/cached value, formula text, and exact
locator.

`XlsxCatalogParser`:

- verifies `.xlsx`, ZIP signature, required OOXML members, and absence of
  encryption;
- rejects workbook external links;
- opens with `read_only=True` twice: once with `data_only=False`, once with
  `data_only=True`;
- never evaluates formulas;
- emits a parser warning when a formula lacks a cached value.

`CsvCatalogParser`:

- requires valid UTF-8;
- uses Python's `csv.Sniffer` with comma, semicolon, and tab delimiters;
- enforces the configured row and column limits;
- retains raw strings without applying numeric coercion.

- [ ] **Step 5: Run parser tests and security-focused cases**

Run: `.venv/bin/pytest tests/cost_data/test_storage.py tests/cost_data/test_parsers.py -q`

Expected: PASS.

- [ ] **Step 6: Commit source storage and parsers**

```bash
git add packages/klave_engine/cost_data/storage.py \
  packages/klave_engine/cost_data/imports tests/cost_data
git commit -m "feat: parse cost catalogs with immutable evidence"
```

---

### Task 5: Mapping, Normalization, and Domain Validation

**Files:**
- Create: `packages/klave_engine/cost_data/schemas.py`
- Create: `packages/klave_engine/cost_data/imports/mapping.py`
- Create: `packages/klave_engine/cost_data/validation.py`
- Test: `tests/cost_data/test_mapping.py`
- Test: `tests/cost_data/test_validation.py`

**Interfaces:**
- Consumes: `ParsedWorkbook`, `UnitRegistry`, `ValidationFinding`
- Produces: `MappingSpec`
- Produces: `BatchDefaults`
- Produces: `NormalizedRow`
- Produces: `normalize_rows(workbook, mapping) -> NormalizationResult`
- Produces: `validate_rows(rows, policy) -> ValidationReport`

- [ ] **Step 1: Write failing normalization and validation tests**

```python
def test_mapping_requires_price_context(parsed_catalog) -> None:
    mapping = MappingSpec(
        sheet_name="CATALOGO",
        header_row=1,
        columns={"source_code": "A", "description": "B", "unit": "C", "price": "E"},
        defaults=BatchDefaults(currency="MXN"),
    )
    report = normalize_rows(parsed_catalog, mapping)
    assert {f.code for f in report.batch_findings} >= {
        "missing_geography",
        "missing_effective_date",
        "missing_tax_basis",
        "missing_cost_basis",
    }


def test_zero_rendimiento_and_duplicate_code_are_blocking() -> None:
    rows = [
        normalized_rendimiento("12118-161", "1.0"),
        normalized_rendimiento("12118-161", "0"),
    ]
    report = validate_rows(rows, ValidationPolicy())
    assert report.blocking_codes == {
        "duplicate_source_code",
        "rendimiento_non_positive",
    }


def test_kg_and_ton_prices_are_equivalent_not_duplicate() -> None:
    rows = [
        normalized_price("ACERO", unit="KG", price="62.72"),
        normalized_price("ACERO", unit="TON", price="62715.68"),
    ]
    report = validate_rows(rows, ValidationPolicy())
    assert "duplicate_source_code" not in report.blocking_codes
    assert "unit_normalized_price_variance" in report.warning_codes


def test_formula_error_is_blocking() -> None:
    row = normalized_row(formula="=#REF!*H196", displayed_value="#REF!")
    report = validate_rows([row], ValidationPolicy())
    assert "spreadsheet_formula_error" in report.blocking_codes
```

- [ ] **Step 2: Run focused tests and verify missing mapping/validation modules**

Run: `.venv/bin/pytest tests/cost_data/test_mapping.py tests/cost_data/test_validation.py -q`

Expected: FAIL on missing interfaces.

- [ ] **Step 3: Implement mapping and normalization contracts**

```python
class BatchDefaults(BaseModel):
    currency: Literal["MXN"] = "MXN"
    region_code: str | None = None
    effective_date: date | None = None
    iva_included: bool | None = None
    cost_basis: CostBasis | None = None


class MappingSpec(BaseModel):
    sheet_name: str
    header_row: int = Field(ge=1)
    columns: dict[str, str]
    row_kind: Literal["concept", "resource", "crew", "rendimiento", "apu", "price"]
    defaults: BatchDefaults

    def stable_hash(self) -> str:
        payload = self.model_dump_json(exclude_none=False)
        return hashlib.sha256(payload.encode()).hexdigest()
```

`normalize_rows` trims Unicode whitespace, normalizes NFC, parses Decimal without
float, maps unit aliases, preserves source locators, and creates batch findings
when required defaults are absent. It does not guess geography, date, IVA, or
cost basis.

```python
class NormalizationResult(BaseModel):
    rows: list[NormalizedRow]
    batch_findings: list[ValidationFinding]


class ValidationReport(BaseModel):
    row_findings: dict[str, list[ValidationFinding]]
    batch_findings: list[ValidationFinding]

    @property
    def blocking_codes(self) -> set[str]:
        return {
            finding.code
            for findings in self.row_findings.values()
            for finding in findings
            if finding.severity == FindingSeverity.BLOCKING
        } | {
            finding.code
            for finding in self.batch_findings
            if finding.severity == FindingSeverity.BLOCKING
        }
```

- [ ] **Step 4: Implement stable validation rules**

Implement rule functions returning `ValidationFinding` with these exact codes:

```text
missing_geography
missing_effective_date
missing_tax_basis
missing_cost_basis
unknown_unit
price_non_positive
rendimiento_non_positive
duplicate_source_code
dimensional_mismatch
arithmetic_mismatch
spreadsheet_formula_error
external_workbook_reference
apu_cycle
percentage_base_missing
expired_observation
unit_normalized_price_variance
stale_observation
```

Arithmetic uses Decimal and a tolerance of
`max(Decimal("0.02"), abs(expected) * Decimal("0.000001"))`. Duplicate codes are
scoped to source system and catalog version. Description equivalence includes
the normalized output dimension so valid `KG` and `TON` alternatives are not
blindly rejected.

- [ ] **Step 5: Run validation tests and type checking**

Run:

```bash
.venv/bin/pytest tests/cost_data/test_mapping.py tests/cost_data/test_validation.py -q
.venv/bin/mypy packages/klave_engine/cost_data
```

Expected: all tests pass and mypy exits 0.

- [ ] **Step 6: Commit normalization and validation**

```bash
git add packages/klave_engine/cost_data/schemas.py \
  packages/klave_engine/cost_data/imports/mapping.py \
  packages/klave_engine/cost_data/validation.py \
  tests/cost_data/test_mapping.py tests/cost_data/test_validation.py
git commit -m "feat: validate mapped cost data"
```

---

### Task 6: Import Staging Service and PostgreSQL Worker

**Files:**
- Create: `packages/klave_engine/cost_data/imports/service.py`
- Create: `apps/worker/__init__.py`
- Create: `apps/worker/main.py`
- Test: `tests/integration/test_import_service.py`
- Test: `tests/integration/test_import_worker.py`

**Interfaces:**
- Consumes: parser, object store, scanner, mapping, validation, repositories
- Produces: `ImportService.create_source(...) -> SourceDocumentResult`
- Produces: `ImportService.create_batch(...) -> ImportBatchResult`
- Produces: `ImportService.process_batch(batch_id: UUID) -> ImportBatchResult`
- Produces: `ImportWorker.run_once() -> bool`

- [ ] **Step 1: Write failing idempotency, quarantine, and worker-claim tests**

```python
def test_same_source_and_mapping_returns_same_batch(import_service, source, mapping) -> None:
    first = import_service.create_batch(source.id, mapping)
    second = import_service.create_batch(source.id, mapping)
    assert first.id == second.id


def test_blocking_rows_are_quarantined_without_partial_publication(
    import_service, invalid_source, mapping
) -> None:
    batch = import_service.create_batch(invalid_source.id, mapping)
    result = import_service.process_batch(batch.id)
    assert result.status == "needs_review"
    assert result.quarantined_rows > 0
    assert result.published_version_id is None


def test_two_workers_cannot_claim_same_job(worker_factory) -> None:
    first = worker_factory("worker-a").claim_next()
    second = worker_factory("worker-b").claim_next()
    assert first is not None
    assert second is None or second.id != first.id
```

- [ ] **Step 2: Run integration tests and verify service failure**

Run:

```bash
KLAVE_TEST_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave_test \
  .venv/bin/pytest tests/integration/test_import_service.py \
  tests/integration/test_import_worker.py -q
```

Expected: FAIL because import orchestration does not exist.

- [ ] **Step 3: Implement import orchestration**

`create_source` streams the upload once while calculating SHA-256, enforces
`max_catalog_upload_bytes`, scans before parsing, stores immutably, and records
rights/geography/date assertions separately from parsed data.

`create_batch`:

```python
mapping_hash = mapping.stable_hash()
existing = repository.find_idempotent_batch(source_id, mapping_hash)
if existing:
    return ImportBatchResult.from_record(existing)
batch = repository.add_batch(source_id, mapping, mapping_hash)
repository.enqueue_job(batch.id)
return ImportBatchResult.from_record(batch)
```

`process_batch` parses, normalizes, validates, stores every staged row, records
counts, and ends in `needs_review`, `validated`, or `failed`. It never publishes.
An unexpected exception rolls back staged writes for that attempt, increments
attempt count, and records a stable error code plus correlation ID.

- [ ] **Step 4: Implement the worker loop**

```python
class ImportWorker:
    def run_once(self) -> bool:
        with self.worker_session_factory.begin() as session:
            job = WorkerImportRepository(session).claim_next_job(self.worker_id)
            if job is None:
                return False
            batch_id = job.import_batch_id
            tenant = TenantContext(
                organization_id=job.organization_id,
                user_id=SERVICE_PRINCIPAL_ID,
                roles={Role.ADMIN},
            )
        self.service.for_tenant(tenant).process_batch(batch_id)
        return True
```

`apps/worker/main.py` supports `--once` for tests/operations and otherwise polls
with a bounded interval no longer than five seconds. Shutdown finishes the
current transaction and stops before claiming another job.

`WorkerImportRepository` is available only from the worker package and uses the
separate `worker_database_url` credential. The API process never imports or
constructs it. After claiming a job, all source, staged-row, and catalog writes
run through the ordinary tenant transaction for `job.organization_id`.

- [ ] **Step 5: Run import service and concurrency tests**

Run:

```bash
KLAVE_TEST_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave_test \
  .venv/bin/pytest tests/integration/test_import_service.py \
  tests/integration/test_import_worker.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit staging and worker behavior**

```bash
git add packages/klave_engine/cost_data/imports/service.py apps/worker \
  tests/integration/test_import_service.py tests/integration/test_import_worker.py
git commit -m "feat: stage catalog imports with durable jobs"
```

---

### Task 7: Publication, Confidence, Approval, and Price Resolution

**Files:**
- Create: `packages/klave_engine/cost_data/confidence.py`
- Create: `packages/klave_engine/cost_data/approvals.py`
- Create: `packages/klave_engine/cost_data/pricing.py`
- Test: `tests/cost_data/test_confidence.py`
- Test: `tests/cost_data/test_approvals.py`
- Test: `tests/integration/test_price_resolution.py`

**Interfaces:**
- Produces: `compute_confidence(evidence) -> ConfidenceGrade`
- Produces: `CatalogPublicationService.publish(version_id: UUID) -> CatalogVersionResult`
- Produces: `CatalogDiffService.compare(base_id, candidate_id) -> CatalogVersionDiff`
- Produces: `ApprovalService.approve_estimate(command) -> ApprovalResult`
- Produces: `PriceResolver.resolve(request) -> PriceResolutionResult`

- [ ] **Step 1: Write failing confidence, approval, and precedence tests**

```python
def test_users_cannot_assign_grade_a_directly() -> None:
    evidence = PriceEvidence(independent_observations=1, metadata_complete=True)
    assert compute_confidence(evidence) == ConfidenceGrade.C


def test_seed_catalog_cannot_publish(publication_service, seed_catalog) -> None:
    with pytest.raises(PublicationBlocked, match="reference-only"):
        publication_service.publish(seed_catalog.id)


def test_controlled_estimate_rejects_self_approval(approval_service) -> None:
    command = ApproveEstimate(
        estimate_id=uuid4(),
        prepared_by=USER_A,
        approved_by=USER_A,
        controlled=True,
        coverage=ConfidenceCoverage(a_or_b_pct=Decimal("100")),
    )
    with pytest.raises(ApprovalBlocked, match="different approver"):
        approval_service.approve_estimate(command)


def test_project_quote_wins_over_org_and_platform_books(price_resolver, request) -> None:
    result = price_resolver.resolve(request)
    assert result.status == "resolved"
    assert result.selected_scope == OwnershipScope.PROJECT
    assert result.reason_code == "approved_project_quote"


def test_missing_price_is_unresolved_not_zero(price_resolver, unknown_request) -> None:
    result = price_resolver.resolve(unknown_request)
    assert result.status == "unresolved"
    assert result.amount is None
```

- [ ] **Step 2: Run tests and confirm the missing services**

Run:

```bash
.venv/bin/pytest tests/cost_data/test_confidence.py tests/cost_data/test_approvals.py -q
KLAVE_TEST_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave_test \
  .venv/bin/pytest tests/integration/test_price_resolution.py -q
```

Expected: FAIL because publication, approval, and pricing services do not exist.

- [ ] **Step 3: Implement evidence-derived confidence and publication gates**

```python
class PriceEvidence(BaseModel):
    independent_observations: int = Field(ge=0)
    metadata_complete: bool
    has_reference_crosscheck: bool = False
    licensed_and_indexed: bool = False
    usage_rights_compatible: bool = False
    has_blocking_finding: bool = False


def compute_confidence(evidence: PriceEvidence) -> ConfidenceGrade:
    if evidence.has_blocking_finding or not evidence.usage_rights_compatible:
        return ConfidenceGrade.REJECTED
    if not evidence.metadata_complete:
        return ConfidenceGrade.SEED
    if evidence.independent_observations >= 3 and evidence.has_reference_crosscheck:
        return ConfidenceGrade.A
    if evidence.independent_observations >= 2 or evidence.licensed_and_indexed:
        return ConfidenceGrade.B
    return ConfidenceGrade.C
```

Publication rejects blocking findings, Seed/Rejected entries, incomplete source
metadata, incompatible rights, or a non-validated draft. It creates a new
immutable version, records warnings and acknowledgements, writes an audit event,
and supersedes the prior active version in one transaction.

When an accepted import contains price observations, publication creates the
matching catalog version and price-book version atomically and returns both IDs.

`CatalogDiffService` compares stable concept/resource/APU identities and returns
separate `added`, `changed`, `retired`, and `conflicted` collections. A changed
record includes field-level `before` and `after` values; it never compares only
display descriptions.

- [ ] **Step 4: Implement ordinary and controlled approval rules**

Issued estimates reject Seed, Rejected, expired, and unresolved prices.
Controlled estimates additionally require a different approver, at least 95% of
direct cost from A/B prices, and a second-approver exception for every C line
contributing at least 1% of direct cost.

```python
class ConfidenceCoverage(BaseModel):
    a_or_b_pct: Decimal = Field(ge=0, le=100)
    c_lines_requiring_exception: list[UUID] = Field(default_factory=list)
    forbidden_line_ids: list[UUID] = Field(default_factory=list)


class ApproveEstimate(BaseModel):
    estimate_id: UUID
    prepared_by: UUID
    approved_by: UUID
    controlled: bool
    coverage: ConfidenceCoverage
    approved_exception_line_ids: list[UUID] = Field(default_factory=list)
```

- [ ] **Step 5: Implement deterministic price resolution**

`PriceResolutionRequest` contains organization, project, item ID, unit, quantity,
region, valuation date, and cost basis. The resolver queries candidates once,
filters expired/incompatible candidates, applies only approved unit conversions,
sorts by the exact precedence in Global Constraints, and returns:

```python
class PriceResolutionResult(BaseModel):
    status: Literal["resolved", "unresolved"]
    amount: Decimal | None
    currency: Literal["MXN"] = "MXN"
    unit_code: str
    selected_observation_id: UUID | None
    selected_price_book_version_id: UUID | None
    selected_scope: OwnershipScope | None
    confidence: ConfidenceGrade | None
    reason_code: str
    alternatives: list[PriceAlternative]
    conversions: list[AppliedConversion]
    warnings: list[ValidationFinding]
```

The resolver does not apply IVA, indirects, financing, utility, or contingency.

- [ ] **Step 6: Run pricing and approval tests**

Run:

```bash
.venv/bin/pytest tests/cost_data/test_confidence.py tests/cost_data/test_approvals.py -q
KLAVE_TEST_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave_test \
  .venv/bin/pytest tests/integration/test_price_resolution.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit publication and pricing**

```bash
git add packages/klave_engine/cost_data/confidence.py \
  packages/klave_engine/cost_data/approvals.py \
  packages/klave_engine/cost_data/pricing.py \
  tests/cost_data/test_confidence.py tests/cost_data/test_approvals.py \
  tests/integration/test_price_resolution.py
git commit -m "feat: publish and resolve trusted prices"
```

---

### Task 8: OIDC Tenant Context, Idempotency, and Cost-Data API

**Files:**
- Modify: `apps/api/dependencies.py:1-110`
- Modify: `apps/api/main.py:1-57`
- Create: `apps/api/auth.py`
- Create: `apps/api/database.py`
- Create: `apps/api/idempotency.py`
- Create: `apps/api/routes/catalog_imports.py`
- Create: `apps/api/routes/catalogs.py`
- Create: `apps/api/routes/price_books.py`
- Test: `tests/integration/test_cost_data_api.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: all services from Tasks 2–7
- Produces: `get_tenant_context() -> TenantContext`
- Produces: source/import/catalog/price-resolution HTTP contracts

- [ ] **Step 1: Write failing authentication, isolation, and idempotency tests**

```python
def test_hosted_request_without_bearer_token_is_401(hosted_client) -> None:
    response = hosted_client.get("/catalogs")
    assert response.status_code == 401


def test_dev_identity_header_is_rejected_when_not_development(hosted_client) -> None:
    response = hosted_client.get(
        "/catalogs",
        headers={"X-Dev-Organization": str(ORG_A), "X-Dev-User": str(USER_A)},
    )
    assert response.status_code == 401


def test_upload_requires_idempotency_key(client) -> None:
    response = client.post("/catalog-sources", files={"file": ("catalog.csv", b"a,b\n")})
    assert response.status_code == 400
    assert response.json()["detail"]["error_type"] == "idempotency_key_required"


def test_cross_tenant_catalog_is_404(client_org_a, catalog_org_b) -> None:
    response = client_org_a.get(f"/catalogs/{catalog_org_b}")
    assert response.status_code == 404
```

- [ ] **Step 2: Run API/auth tests and verify missing routes**

Run:

```bash
.venv/bin/pytest tests/test_auth.py -q
KLAVE_TEST_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave_test \
  .venv/bin/pytest tests/integration/test_cost_data_api.py -q
```

Expected: FAIL with missing auth and route modules.

- [ ] **Step 3: Implement OIDC verification and request-scoped tenant sessions**

`OidcVerifier` uses `jwt.PyJWKClient` with configured issuer, audience, algorithms
restricted to `RS256`, and cached keys. The subject maps to `User`; the requested
organization must be present in `Membership`.

Hosted requests select an organization with `X-Organization-ID`; the dependency
returns 403 unless the authenticated subject has an active membership in that
organization. In explicit development mode only, `X-Dev-Organization` and
`X-Dev-User` create the context after verifying the stored membership. A header
alone never creates a user or membership.

`get_database_session` starts a transaction, sets
`klave.organization_id`, yields the session, commits on success, and rolls back on
error.

- [ ] **Step 4: Implement idempotent mutation guard**

Require `Idempotency-Key` for uploads, batch creation, publication, approvals,
and price-book mutations. Store organization, route, key, request hash, status,
and response JSON. Reusing a key with a different request hash returns 409.

- [ ] **Step 5: Implement the first API surface**

```text
POST   /catalog-sources
POST   /catalog-imports
GET    /catalog-imports/{batch_id}
GET    /catalog-imports/{batch_id}/rows
PATCH  /catalog-imports/{batch_id}/rows/{row_id}
POST   /catalog-imports/{batch_id}/validate
POST   /catalog-imports/{batch_id}/publish
GET    /catalogs
GET    /catalogs/{catalog_id}/versions
GET    /catalog-versions/{version_id}
GET    /catalog-versions/{version_id}/diff
GET    /price-books
POST   /price-resolutions
GET    /price-observations/{observation_id}/provenance
```

Lists accept `limit` from 1–100 and non-negative `offset`. Routes check role
requirements and return stable Spanish error messages with machine-readable
`error_type`.

- [ ] **Step 6: Register routers and run API contract tests**

Run:

```bash
.venv/bin/pytest tests/test_auth.py -q
KLAVE_TEST_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave_test \
  .venv/bin/pytest tests/integration/test_cost_data_api.py -q
.venv/bin/mypy apps/api packages/klave_engine/cost_data
```

Expected: PASS and mypy exit 0.

- [ ] **Step 7: Commit the tenant-scoped API**

```bash
git add apps/api packages/klave_engine/cost_data tests/test_auth.py \
  tests/integration/test_cost_data_api.py
git commit -m "feat: expose tenant-scoped catalog API"
```

---

### Task 9: Evidence-Bearing Price Provider for Existing Costing

**Files:**
- Create: `packages/klave_engine/costing/price_provider.py`
- Modify: `packages/klave_engine/costing/models.py:1-200`
- Modify: `packages/klave_engine/costing/apu.py:1-86`
- Modify: `packages/klave_engine/costing/report.py:1-220`
- Modify: `packages/klave_engine/costing/recompute.py:1-115`
- Modify: `apps/api/routes/reports.py:1-180`
- Test: `tests/test_costing.py`
- Test: `tests/integration/test_costing_price_provider.py`

**Interfaces:**
- Consumes: `PriceResolver`
- Produces: `PriceProvider.resolve_many(resource_codes, context) -> ResolvedPriceBook`
- Produces: `PriceProvider.load_apus(concept_codes, context) -> ResolvedApuSet`
- Produces: `LegacySeedPriceProvider`
- Produces: `DatabasePriceProvider`
- Extends: `CostReport.pricing_snapshot`

- [ ] **Step 1: Write failing prototype and trusted-provider tests**

```python
def test_legacy_seed_report_is_explicitly_untrusted(sample_detections) -> None:
    report = generate_cost_report(
        "p1",
        sample_detections,
        METERS,
        CostingConfig(),
        price_provider=LegacySeedPriceProvider(),
    )
    assert report.pricing_snapshot.prototype is True
    assert report.pricing_snapshot.can_issue is False
    assert all(item.confidence == "Seed" for item in report.pricing_snapshot.items)


def test_database_provider_records_version_and_observation_ids(
    trusted_provider, sample_detections
) -> None:
    report = generate_cost_report(
        "p1",
        sample_detections,
        METERS,
        CostingConfig(),
        price_provider=trusted_provider,
    )
    assert report.pricing_snapshot.prototype is False
    assert report.pricing_snapshot.price_book_version_ids
    assert report.pricing_snapshot.apu_ids
    assert all(item.observation_id for item in report.pricing_snapshot.items)


def test_unresolved_resource_blocks_cost_report(blocking_provider, sample_detections) -> None:
    with pytest.raises(ReportGenerationError, match="unresolved price"):
        generate_cost_report(
            "p1",
            sample_detections,
            METERS,
            CostingConfig(),
            price_provider=blocking_provider,
        )
```

- [ ] **Step 2: Run tests and verify the provider interface is missing**

Run:

```bash
.venv/bin/pytest tests/test_costing.py \
  tests/integration/test_costing_price_provider.py -q
```

Expected: FAIL on missing `price_provider`.

- [ ] **Step 3: Implement the compatibility port**

```python
class ResolvedResourcePrice(BaseModel):
    resource_code: str
    amount: Decimal | None
    unit_code: str
    confidence: ConfidenceGrade
    observation_id: UUID | None = None
    price_book_version_id: UUID | None = None
    reason_code: str


class PriceProvider(Protocol):
    def resolve_many(
        self, resource_codes: Sequence[str], context: PricingContext
    ) -> ResolvedPriceBook: ...

    def load_apus(
        self, concept_codes: Sequence[str], context: PricingContext
    ) -> ResolvedApuSet: ...
```

`LegacySeedPriceProvider` reads the existing hard-coded resources and labels
every item Seed. `DatabasePriceProvider` maps legacy resource codes through
`ConceptAlias`/resource aliases, loads the approved APU and components for each
concept, and calls `PriceResolver` for component prices. Any missing APU,
component, or price is unresolved.

- [ ] **Step 4: Attach immutable pricing evidence to cost reports**

Add:

```python
class PricingSnapshot(BaseModel):
    prototype: bool
    can_issue: bool
    price_book_version_ids: list[UUID]
    apu_ids: list[UUID]
    items: list[ResolvedResourcePrice]


class CostReport(BaseModel):
    # existing fields remain
    pricing_snapshot: PricingSnapshot
```

`build_apu` receives a resolved resource map and APU template rather than reading
`RESOURCES` or `APU_TEMPLATES` internally. Convert Decimal to float only at the
final legacy Pydantic boundary, after preserving the original Decimal string in
the snapshot.

- [ ] **Step 5: Gate recompute and issued-budget behavior**

Add `CostingPriceMode = Literal["prototype", "resolved"]` to the recompute
request together with optional `valuation_date` and `region_code`. Prototype
mode uses `LegacySeedPriceProvider` and always emits `can_issue=False`. Resolved
mode requires both valuation date and region, rejects direct `insumo_prices`
overrides, requires a database provider, and fails on any unresolved APU or
resource.

Keep `prototype` as the default so existing clients remain compatible:

```python
class CostingOverrides(BaseModel):
    # existing fields remain
    price_mode: Literal["prototype", "resolved"] = "prototype"
    valuation_date: date | None = None
    region_code: str | None = None
```

Do not add an issue/approve endpoint in this task; the evidence flag is the
contract consumed by the later budget workflow.

- [ ] **Step 6: Run costing regression and provider tests**

Run:

```bash
.venv/bin/pytest tests/test_costing.py \
  tests/integration/test_costing_price_provider.py \
  tests/test_api_contracts.py -q
```

Expected: PASS, with existing cost calculations unchanged in prototype mode.

- [ ] **Step 7: Commit the costing adapter**

```bash
git add packages/klave_engine/costing apps/api/routes/reports.py \
  tests/test_costing.py tests/test_api_contracts.py \
  tests/integration/test_costing_price_provider.py
git commit -m "feat: attach price evidence to cost reports"
```

---

### Task 10: Redacted Seed Fixtures and Deterministic Import Regression

**Files:**
- Modify: `packages/klave_engine/cli.py:1-80`
- Create: `packages/klave_engine/cost_data/seed_import.py`
- Create: `tests/cost_data/fixtures/rendimientos_seed.csv`
- Create: `tests/cost_data/fixtures/labor_catalog_seed.csv`
- Create: `tests/cost_data/fixtures/composite_prices_seed.csv`
- Create: `tests/cost_data/fixtures/broken_quantity_seed.xlsx`
- Create: `tests/cost_data/test_seed_regressions.py`
- Create: `tests/cost_data/test_seed_import_cli.py`
- Create: `docs/COST_DATA_IMPORTS.md`

**Interfaces:**
- Consumes: import parsers, mapping, validation
- Produces: rights-safe minimized fixtures reproducing supplied-workbook schemas
- Produces: documented Klave Excel/CSV column contracts
- Produces: private `klave cost-data import-seed` command

- [ ] **Step 1: Write failing regression expectations**

```python
def test_rendimiento_seed_quarantines_zero_and_duplicate(import_fixture) -> None:
    report = import_fixture("rendimientos_seed.csv")
    assert report.blocking_counts == {
        "duplicate_source_code": 2,
        "rendimiento_non_positive": 1,
    }


def test_composite_seed_accepts_kg_and_ton_equivalents(import_fixture) -> None:
    report = import_fixture("composite_prices_seed.csv")
    assert report.accepted_rows == 2
    assert report.blocking_count == 0


def test_broken_quantity_workbook_never_becomes_catalog_truth(import_fixture) -> None:
    report = import_fixture("broken_quantity_seed.xlsx")
    assert report.blocking_counts["spreadsheet_formula_error"] >= 1
    assert report.publishable is False


def test_seed_cli_requires_explicit_rights_and_never_publishes(runner, seed_csv) -> None:
    missing = runner.invoke(app, ["cost-data", "import-seed", str(seed_csv)])
    assert missing.exit_code != 0
    assert "--usage-rights" in missing.output

    imported = runner.invoke(
        app,
        [
            "cost-data", "import-seed", str(seed_csv),
            "--organization-id", str(ORG_A),
            "--usage-rights", "internal_only",
        ],
    )
    assert imported.exit_code == 0
    assert "reference-only" in imported.output
    assert "published" not in imported.output.lower()
```

- [ ] **Step 2: Run regression tests and verify fixtures are missing**

Run:

```bash
.venv/bin/pytest tests/cost_data/test_seed_regressions.py \
  tests/cost_data/test_seed_import_cli.py -q
```

Expected: FAIL because minimized fixtures do not exist.

- [ ] **Step 3: Create minimized, synthetic fixtures**

Create only the rows needed to reproduce:

- a duplicate code and zero rendimiento;
- labor-only price metadata;
- a `KG`/`TON` equivalent pair;
- one `#REF!`, one `#DIV/0!`, and one external-link formula.

Do not copy full descriptions, proprietary catalogs, or the supplied workbooks
into the repository. Add a fixture header stating that values and descriptions
are synthetic regression data.

- [ ] **Step 4: Implement the private Seed import command**

Register a Typer sub-application named `cost-data`. Implement:

```text
klave cost-data import-seed FILE...
  --organization-id UUID
  --usage-rights {internal_only,derived_use,redistribution}
  --region-code TEXT
  --effective-date YYYY-MM-DD
  --dry-run
```

The command uses the same `ImportService` as the API. It sets confidence to
Seed, `reference_only=True`, and never calls publication. `--dry-run` parses,
maps, and validates without persisting a source document. The command prints the
source hash, accepted/quarantined counts, missing metadata, and resulting draft
batch ID.

After implementation, privately ingest the six supplied files into the
development organization using `--usage-rights internal_only`; do not move or
copy the raw workbooks into the Git repository.

- [ ] **Step 5: Document import contracts and error codes**

`docs/COST_DATA_IMPORTS.md` documents:

- accepted file types and limits;
- required columns for concept, resource, rendimiento, APU, and quotation files;
- required batch defaults;
- canonical units and aliases;
- blocking/warning codes;
- Seed/reference-only behavior;
- exact publication lifecycle; and
- a complete Spanish CSV example using synthetic values.

- [ ] **Step 6: Run seed and CLI regressions**

Run:

```bash
.venv/bin/pytest tests/cost_data/test_seed_regressions.py \
  tests/cost_data/test_seed_import_cli.py -q
```

Expected: PASS with the exact finding counts above.

- [ ] **Step 7: Commit fixtures, private importer, and documentation**

```bash
git add packages/klave_engine/cli.py packages/klave_engine/cost_data/seed_import.py \
  tests/cost_data/fixtures tests/cost_data/test_seed_regressions.py \
  tests/cost_data/test_seed_import_cli.py docs/COST_DATA_IMPORTS.md
git commit -m "test: cover seed catalog import failures"
```

---

### Task 11: Full Vertical-Slice Acceptance, CI, and Operational Commands

**Files:**
- Modify: `Makefile`
- Modify: `apps/api/routes/projects.py:1-220`
- Modify: `apps/api/routes/reports.py:1-180`
- Modify: `apps/api/dependencies.py:1-110`
- Create: `.github/workflows/ci.yml`
- Create: `tests/integration/test_cost_data_vertical_slice.py`
- Modify: `README.md`
- Modify: `docs/DATA_CONTRACTS.md`

**Interfaces:**
- Consumes: every preceding task
- Produces: reproducible local/CI verification
- Produces: one end-to-end tenant-safe import-to-cost-report workflow

- [ ] **Step 1: Write the failing vertical-slice acceptance test**

```python
def test_import_publish_resolve_and_cost_report(
    org_a_client, org_b_client, valid_catalog_csv, processed_project
) -> None:
    source = upload_source(org_a_client, valid_catalog_csv)
    batch = create_and_process_import(org_a_client, source)
    assert batch["blocking_count"] == 0

    version = publish_import(org_a_client, batch)
    assert version["status"] == "published"

    resolution = org_a_client.post(
        "/price-resolutions",
        json=resolution_request(version),
    ).json()
    assert resolution["status"] == "resolved"
    assert resolution["selected_price_book_version_id"] == version["price_book_version_id"]

    report = recompute_with_resolved_prices(org_a_client, processed_project)
    assert report["pricing_snapshot"]["prototype"] is False
    assert report["pricing_snapshot"]["can_issue"] is True

    assert org_b_client.get(f"/catalog-versions/{version['id']}").status_code == 404
```

- [ ] **Step 2: Run the acceptance test and verify project/pricing wiring fails**

Run:

```bash
KLAVE_TEST_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave_test \
  .venv/bin/pytest tests/integration/test_cost_data_vertical_slice.py -q
```

Expected: FAIL because `POST /projects` has not yet inserted `ProjectAccess`, and
the recompute route has not yet selected `DatabasePriceProvider` for resolved
mode.

- [ ] **Step 3: Wire project authorization and resolved recompute**

In `apps/api/routes/projects.py`, after creating/registering a project, insert:

```python
project_access_repository.add(
    project_id=manifest.project_id,
    organization_id=tenant.organization_id,
)
```

All project read/process/report routes must load `ProjectAccess` through the
tenant transaction before calling the existing filesystem `ProjectStore`.

In `apps/api/routes/reports.py`, construct `DatabasePriceProvider` when the
request mode is `resolved`, using the active organization/project context,
valuation date, region, and direct cost basis. Keep
`LegacySeedPriceProvider` only for explicit `prototype` mode.

Emit `project_registered` and `cost_report_recomputed` audit events in the same
transactions as their database state changes.

- [ ] **Step 4: Add local commands and PostgreSQL-backed CI**

Add Make targets:

```make
db-up:
	docker compose up -d postgres

db-migrate:
	.venv/bin/alembic upgrade head

worker-once:
	.venv/bin/python -m apps.worker.main --once

test-cost-data:
	.venv/bin/pytest tests/cost_data tests/integration -q
```

The GitHub Actions workflow runs PostgreSQL 16 as a service, installs with
`uv sync --all-groups`, migrates the test database, and runs:

```bash
.venv/bin/ruff check .
.venv/bin/mypy packages/klave_engine apps/api
.venv/bin/pytest -q
npm --prefix apps/web ci
npm --prefix apps/web run lint
npm --prefix apps/web run build
```

- [ ] **Step 5: Update product and data-contract documentation**

README additions include database startup, migrations, worker startup, local
development identity, and a warning that prototype Seed budgets cannot be
issued. `docs/DATA_CONTRACTS.md` adds source, import, catalog version,
price-resolution, and pricing-snapshot contracts.

- [ ] **Step 6: Run the complete verification suite**

Run:

```bash
docker compose up -d postgres
KLAVE_TEST_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave_test \
  .venv/bin/alembic upgrade head
.venv/bin/ruff check .
.venv/bin/mypy packages/klave_engine apps/api
KLAVE_TEST_DATABASE_URL=postgresql+psycopg://klave:klave@127.0.0.1:5432/klave_test \
  .venv/bin/pytest -q
npm --prefix apps/web ci
npm --prefix apps/web run lint
npm --prefix apps/web run build
```

Expected:

```text
Ruff: exit 0
mypy: exit 0
pytest: 0 failures
ESLint: exit 0
Next.js production build: exit 0
```

- [ ] **Step 7: Commit the verified vertical slice**

```bash
git add Makefile .github/workflows/ci.yml README.md docs/DATA_CONTRACTS.md \
  tests/integration/test_cost_data_vertical_slice.py
git commit -m "feat: complete cost data foundation vertical slice"
```

---

## Completion Gate

Do not declare this plan complete until all of the following are demonstrated by
fresh command output:

- migrations apply cleanly to an empty PostgreSQL database;
- RLS prevents cross-tenant reads and writes;
- CSV and XLSX evidence survives parsing with exact source locators;
- invalid rows quarantine deterministically;
- a validated import publishes an immutable version;
- Seed imports cannot publish or issue a budget;
- price resolution follows the approved precedence;
- unresolved prices never become zero;
- the legacy engine emits a pricing snapshot;
- prototype reports are non-issuable;
- resolved reports identify source observations and price-book versions; and
- the full Python and frontend regression suites pass.
