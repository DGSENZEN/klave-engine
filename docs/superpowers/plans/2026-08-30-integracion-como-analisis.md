# Integración como análisis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the six flat integration percentages with real analyses — itemized desglose de indirectos (campo + oficina central), financiamiento computed from the flujo at a captured tasa, itemized cargos adicionales — in dual mode: percentages stay as the stamped fallback, amounts win when an analysis exists.

**Architecture:** New pure-arithmetic module `costing/indirectos.py` (models + documento builders; imports nothing from `models.py` because `models.py` imports *it*). A resolver in `costing/integration.py` turns config + workspace data + flujo into per-component `ComponenteResuelto` (amount|pct + fuente). `report.py` reorders the pipeline (schedule → iterate integrate ⇄ flujo) because financiamiento needs the flujo. Exports print stored documentos, never recompute. Workspace data rides `workspace_settings`; project data rides `CostingConfig` overrides.

**Tech Stack:** Python 3.12, pydantic v2, FastAPI, SQLite (stdlib), openpyxl, Next.js + TS + Tailwind (apps/web), pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-integracion-como-analisis-design.md`

## Global Constraints

- **Declared mode is bit-for-bit today's output.** `pytest tests/test_gold_money.py tests/test_obra_api.py` must pass unchanged after every task. Demo baseline direct cost `157533681.21` never moves — integration must never feed back into direct cost.
- **No invented numbers.** Missing datum ⇒ that component stays declared, visibly, with a warning naming what is missing — but only when something was *partially* captured (nothing captured at all ⇒ silent declared mode, same doctrine as the plantilla: "no se avisa cuando falta").
- Rubro `importe: 0` = **sin capturar**: excluded from totals, flagged, never a zero-that-reads-as-free.
- Legal article numbers appear ONLY in the module docstring of `costing/indirectos.py` (the RLOPSRM is overdue for replacement; grep the codebase — `escalatoria.py`, `plantilla.py` — for the house pattern).
- Docstrings/comments in Spanish, house voice (read `escalatoria.py`'s docstring first). Code identifiers may be English or Spanish following the file you touch.
- Tests use hand-computed fixtures, never snapshots. API tests use the `data_dir` fixture (tests/conftest.py) + the `_client(monkeypatch)` pattern from `tests/test_catalog_previews_api.py` verbatim.
- The API preview server is NOT `--reload`: restart it after engine changes if manually verifying.
- **apps/web:** this Next.js version has breaking changes — read the relevant guide in `apps/web/node_modules/next/dist/docs/` before writing any web code. Follow token/dark-mode conventions of neighboring components.
- Commit messages in Spanish, imperative, ending with:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`

---

### Task 1: Modelos y aritmética del desglose (`indirectos.py`)

**Files:**
- Create: `packages/klave_engine/costing/indirectos.py`
- Test: `tests/test_indirectos.py`

**Interfaces:**
- Consumes: nothing project-internal (pydantic only — this module must NOT import `klave_engine.costing.models`; `models.py` will import it in Task 3).
- Produces (later tasks rely on these exact names):
  - `CategoriaRubro`, `CATEGORIA_LABEL: dict[str, str]`
  - `RubroIndirecto(concepto: str, categoria: CategoriaRubro = "servicios", importe: float = 0.0, base: Literal["mensual","unico"] = "mensual")`
  - `DesgloseCampo(rubros: list[RubroIndirecto] = [])`
  - `DesgloseOficinaCentral(rubros: list[RubroIndirecto] = [], volumen_anual_contratado: float = 0.0)`
  - `AnalisisFinanciamiento(tasa_anual: float = 0.0, indicador: str = "", fuente: str = "", fecha_publicacion: str = "")` with `.faltantes() -> list[str]` and `.completo -> bool` (property)
  - `CargoAdicional(concepto: str, base_legal: str = "", pct: float = 0.0)`
  - `RenglonDocumento(concepto, categoria, base, importe, sin_capturar: bool = False, fuente: str = "capturado")`
  - `DocumentoDesglose(renglones: list[RenglonDocumento] = [], total: float = 0.0, notas: list[str] = [])`
  - `documenta_campo(desglose: DesgloseCampo, meses: int, plantilla_total: float, cargos_sin_sueldo: int) -> DocumentoDesglose`
  - `documenta_oficina(oficina: DesgloseOficinaCentral, costo_directo: float) -> DocumentoDesglose | None`
  - `ComponenteResuelto(code: str, amount: float | None = None, pct: float = 0.0, fuente: Literal["analisis","declarado"] = "declarado", documento: dict = {}, faltantes: list[str] = [])`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_indirectos.py`:

```python
"""Desglose de indirectos: la aritmética del documento, a mano."""

from klave_engine.costing.indirectos import (
    AnalisisFinanciamiento,
    DesgloseCampo,
    DesgloseOficinaCentral,
    RubroIndirecto,
    documenta_campo,
    documenta_oficina,
)


def test_campo_mensual_por_meses_y_unicos_una_vez():
    desglose = DesgloseCampo(rubros=[
        RubroIndirecto(concepto="Renta de bodega", categoria="depreciacion_mantenimiento_rentas",
                       importe=10_000.0, base="mensual"),
        RubroIndirecto(concepto="Fianza de cumplimiento", categoria="seguros_fianzas",
                       importe=30_000.0, base="unico"),
    ])
    doc = documenta_campo(desglose, meses=6, plantilla_total=120_000.0, cargos_sin_sueldo=0)
    # 10,000 × 6 + 30,000 + 120,000 de plantilla = 210,000
    assert doc.total == 210_000.0
    personal = doc.renglones[0]
    assert personal.fuente == "plantilla de campo" and personal.importe == 120_000.0
    assert not any(r.sin_capturar for r in doc.renglones)


def test_campo_rubro_sin_importe_queda_visible_y_fuera_del_total():
    desglose = DesgloseCampo(rubros=[
        RubroIndirecto(concepto="Renta de bodega", importe=10_000.0, base="mensual"),
        RubroIndirecto(concepto="Vehículo de residente", importe=0.0, base="mensual"),
    ])
    doc = documenta_campo(desglose, meses=3, plantilla_total=0.0, cargos_sin_sueldo=0)
    assert doc.total == 30_000.0  # el rubro sin capturar no suma
    vacio = next(r for r in doc.renglones if r.concepto == "Vehículo de residente")
    assert vacio.sin_capturar and vacio.importe == 0.0
    assert any("sin importe capturado" in n for n in doc.notas)


def test_campo_plantilla_incompleta_se_dice():
    doc = documenta_campo(DesgloseCampo(), meses=4, plantilla_total=80_000.0, cargos_sin_sueldo=2)
    assert doc.total == 80_000.0
    assert any("sin sueldo" in n for n in doc.notas)


def test_oficina_prorratea_por_volumen_anual():
    oficina = DesgloseOficinaCentral(
        rubros=[RubroIndirecto(concepto="Renta de oficina", importe=600_000.0),
                RubroIndirecto(concepto="Nómina administrativa", importe=1_400_000.0)],
        volumen_anual_contratado=40_000_000.0,
    )
    doc = documenta_oficina(oficina, costo_directo=10_000_000.0)
    # 2,000,000 / 40,000,000 = 5 % → 500,000 en esta obra
    assert doc is not None and doc.total == 500_000.0
    assert any("5.0000 %" in n for n in doc.notas)


def test_oficina_sin_volumen_no_hay_analisis():
    oficina = DesgloseOficinaCentral(
        rubros=[RubroIndirecto(concepto="Renta", importe=600_000.0)],
        volumen_anual_contratado=0.0,
    )
    assert documenta_oficina(oficina, costo_directo=10_000_000.0) is None


def test_financiamiento_faltantes_nombra_lo_que_falta():
    a = AnalisisFinanciamiento(tasa_anual=12.0, indicador="TIIE 28 días")
    assert not a.completo
    assert a.faltantes() == ["fuente", "fecha de publicación"]
    b = AnalisisFinanciamiento(tasa_anual=12.0, indicador="TIIE 28 días",
                               fuente="Banxico SF43783", fecha_publicacion="2026-08-27")
    assert b.completo and b.faltantes() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_indirectos.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'klave_engine.costing.indirectos'`

- [ ] **Step 3: Write the module**

Create `packages/klave_engine/costing/indirectos.py`. The docstring is part of the deliverable — write it in the voice of `escalatoria.py` (read that file first). It must state: what a desglose is and why a bare percentage is the disqualifiable document; that the personal de campo line comes from the plantilla and is never typed twice; that the oficina central percentage is *derived* (costo anual ÷ volumen anual, which is what prorating means); that a tasa without indicador+fuente+fecha is not a tasa; and that this is the ONE place article numbers may be cited (RLOPSRM arts. 211–220 territory).

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CategoriaRubro = Literal[
    "honorarios_prestaciones",
    "depreciacion_mantenimiento_rentas",
    "servicios",
    "fletes_acarreos",
    "gastos_oficina",
    "capacitacion",
    "seguridad_higiene",
    "seguros_fianzas",
    "trabajos_previos_auxiliares",
]

CATEGORIA_LABEL: dict[str, str] = {
    "honorarios_prestaciones": "Honorarios, sueldos y prestaciones",
    "depreciacion_mantenimiento_rentas": "Depreciación, mantenimiento y rentas",
    "servicios": "Servicios",
    "fletes_acarreos": "Fletes y acarreos",
    "gastos_oficina": "Gastos de oficina",
    "capacitacion": "Capacitación y adiestramiento",
    "seguridad_higiene": "Seguridad e higiene",
    "seguros_fianzas": "Seguros y fianzas",
    "trabajos_previos_auxiliares": "Trabajos previos y auxiliares",
}


class RubroIndirecto(BaseModel):
    concepto: str
    categoria: CategoriaRubro = "servicios"
    # 0 = sin capturar: el renglón se ve vacío y no suma. Nunca es "gratis".
    importe: float = 0.0
    base: Literal["mensual", "unico"] = "mensual"


class DesgloseCampo(BaseModel):
    rubros: list[RubroIndirecto] = Field(default_factory=list)


class DesgloseOficinaCentral(BaseModel):
    # Importes ANUALES; ``base`` se ignora aquí.
    rubros: list[RubroIndirecto] = Field(default_factory=list)
    # 0 = sin capturar: sin volumen no hay prorrateo y no hay análisis.
    volumen_anual_contratado: float = 0.0


class AnalisisFinanciamiento(BaseModel):
    tasa_anual: float = 0.0
    indicador: str = ""       # p. ej. "TIIE 28 días"
    fuente: str = ""          # de dónde salió la tasa
    fecha_publicacion: str = ""  # ISO

    def faltantes(self) -> list[str]:
        missing: list[str] = []
        if self.tasa_anual <= 0:
            missing.append("tasa")
        if not self.indicador.strip():
            missing.append("indicador")
        if not self.fuente.strip():
            missing.append("fuente")
        if not self.fecha_publicacion.strip():
            missing.append("fecha de publicación")
        return missing

    @property
    def completo(self) -> bool:
        return not self.faltantes()


class CargoAdicional(BaseModel):
    concepto: str
    base_legal: str = ""
    pct: float = 0.0


class RenglonDocumento(BaseModel):
    concepto: str
    categoria: str
    base: str
    importe: float
    sin_capturar: bool = False
    fuente: str = "capturado"


class DocumentoDesglose(BaseModel):
    renglones: list[RenglonDocumento] = Field(default_factory=list)
    total: float = 0.0
    notas: list[str] = Field(default_factory=list)


class ComponenteResuelto(BaseModel):
    """Un componente de la integración con su fuente dicha.

    ``amount`` presente = lo respalda un análisis y el importe manda;
    ``amount`` en None = porcentaje declarado, y el reporte lo dice."""

    code: str  # "CI-C" | "CI-O" | "FI" | "UT" | "CA"
    amount: float | None = None
    pct: float = 0.0
    fuente: Literal["analisis", "declarado"] = "declarado"
    documento: dict = Field(default_factory=dict)
    faltantes: list[str] = Field(default_factory=list)


def documenta_campo(
    desglose: DesgloseCampo, meses: int, plantilla_total: float, cargos_sin_sueldo: int
) -> DocumentoDesglose:
    meses = max(1, meses)
    renglones: list[RenglonDocumento] = []
    notas: list[str] = []
    total = 0.0
    if plantilla_total > 0 or cargos_sin_sueldo:
        renglones.append(RenglonDocumento(
            concepto="Personal técnico, administrativo y de servicio de campo",
            categoria="honorarios_prestaciones", base="mensual",
            importe=round(plantilla_total, 2), fuente="plantilla de campo",
        ))
        total += plantilla_total
    for rubro in desglose.rubros:
        if rubro.importe <= 0:
            renglones.append(RenglonDocumento(
                concepto=rubro.concepto, categoria=rubro.categoria,
                base=rubro.base, importe=0.0, sin_capturar=True,
            ))
            continue
        importe = round(rubro.importe * meses, 2) if rubro.base == "mensual" else round(rubro.importe, 2)
        total += importe
        renglones.append(RenglonDocumento(
            concepto=rubro.concepto, categoria=rubro.categoria,
            base=rubro.base, importe=importe,
        ))
    vacios = sum(1 for r in renglones if r.sin_capturar)
    if vacios:
        notas.append(
            f"{vacios} {'renglón' if vacios == 1 else 'renglones'} sin importe "
            "capturado: el total está incompleto en esa medida."
        )
    if cargos_sin_sueldo:
        notas.append(
            f"{cargos_sin_sueldo} {'cargo' if cargos_sin_sueldo == 1 else 'cargos'} "
            "de la plantilla sin sueldo capturado: el rubro de personal está incompleto."
        )
    notas.append(f"Rubros mensuales multiplicados por los {meses} meses del programa.")
    return DocumentoDesglose(renglones=renglones, total=round(total, 2), notas=notas)


def documenta_oficina(
    oficina: DesgloseOficinaCentral, costo_directo: float
) -> DocumentoDesglose | None:
    """None cuando falta el volumen anual o no hay un solo rubro con importe:
    sin esos datos el prorrateo sería un número inventado."""
    if oficina.volumen_anual_contratado <= 0:
        return None
    renglones: list[RenglonDocumento] = []
    anual = 0.0
    for rubro in oficina.rubros:
        if rubro.importe <= 0:
            renglones.append(RenglonDocumento(
                concepto=rubro.concepto, categoria=rubro.categoria,
                base="anual", importe=0.0, sin_capturar=True,
            ))
            continue
        anual += rubro.importe
        renglones.append(RenglonDocumento(
            concepto=rubro.concepto, categoria=rubro.categoria,
            base="anual", importe=round(rubro.importe, 2),
        ))
    if anual <= 0:
        return None
    pct = anual / oficina.volumen_anual_contratado * 100.0
    total = round(costo_directo * pct / 100.0, 2)
    notas = [
        f"Costo anual de oficina central ${anual:,.2f} ÷ volumen anual contratado "
        f"${oficina.volumen_anual_contratado:,.2f} = {pct:.4f} % aplicado al costo "
        "directo de esta obra."
    ]
    vacios = sum(1 for r in renglones if r.sin_capturar)
    if vacios:
        notas.append(
            f"{vacios} {'renglón' if vacios == 1 else 'renglones'} sin importe "
            "capturado: el porcentaje está incompleto en esa medida."
        )
    return DocumentoDesglose(renglones=renglones, total=total, notas=notas)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_indirectos.py -v`
Expected: 6 PASS

- [ ] **Step 5: Commit**

```bash
git add packages/klave_engine/costing/indirectos.py tests/test_indirectos.py
git commit -m "feat(costing): desglose de indirectos — rubros de campo y oficina central con su aritmética documentada

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Aritmética del financiamiento

**Files:**
- Modify: `packages/klave_engine/costing/indirectos.py` (append)
- Test: `tests/test_indirectos.py` (append)

**Interfaces:**
- Produces:
  - `PeriodoFinanciamiento(periodo: int, egresos: float, ingresos: float, saldo: float, costo: float)`
  - `DocumentoFinanciamiento(tasa_anual: float, indicador: str, fuente: str, fecha_publicacion: str, periodos: list[PeriodoFinanciamiento] = [], total: float = 0.0)`
  - `compute_financiamiento(analisis: AnalisisFinanciamiento, egresos: list[float], ingresos: list[float]) -> DocumentoFinanciamiento`

- [ ] **Step 1: Write the failing tests** (append to `tests/test_indirectos.py`)

```python
from klave_engine.costing.indirectos import compute_financiamiento


def _analisis():
    return AnalisisFinanciamiento(tasa_anual=12.0, indicador="TIIE 28 días",
                                  fuente="Banxico SF43783", fecha_publicacion="2026-08-27")


def test_financiamiento_a_mano():
    # Tasa 12 % anual → 1 % mensual. Mes 1: saldo 100, costo 1.00.
    # Mes 2: saldo 100+100−250 = −50, costo −0.50. Total 0.50.
    doc = compute_financiamiento(_analisis(), egresos=[100.0, 100.0], ingresos=[0.0, 250.0])
    assert [p.saldo for p in doc.periodos] == [100.0, -50.0]
    assert [p.costo for p in doc.periodos] == [1.0, -0.5]
    assert doc.total == 0.5
    assert doc.indicador == "TIIE 28 días" and doc.fecha_publicacion == "2026-08-27"


def test_financiamiento_negativo_se_conserva():
    # Anticipo grande: el contratista trabaja con dinero ajeno y el costo es
    # negativo. Se conserva, jamás se recorta a cero.
    doc = compute_financiamiento(_analisis(), egresos=[100.0, 100.0], ingresos=[150.0, 50.0])
    assert [p.saldo for p in doc.periodos] == [-50.0, 0.0]
    assert doc.total == -0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_indirectos.py -v -k financiamiento_`
Expected: FAIL — `ImportError: cannot import name 'compute_financiamiento'` (the faltantes test from Task 1 still passes)

- [ ] **Step 3: Implement** (append to `indirectos.py`)

```python
class PeriodoFinanciamiento(BaseModel):
    periodo: int
    egresos: float
    ingresos: float
    saldo: float   # acumulado: lo gastado que nadie ha pagado todavía
    costo: float   # saldo × tasa del periodo; negativo cuando el anticipo financia


class DocumentoFinanciamiento(BaseModel):
    tasa_anual: float
    indicador: str
    fuente: str
    fecha_publicacion: str
    periodos: list[PeriodoFinanciamiento] = Field(default_factory=list)
    total: float = 0.0


def compute_financiamiento(
    analisis: AnalisisFinanciamiento, egresos: list[float], ingresos: list[float]
) -> DocumentoFinanciamiento:
    """El costo de traer dinero puesto antes de que lo paguen.

    ``egresos`` e ``ingresos`` van por periodo del flujo (meses); la tasa del
    periodo es la anual entre doce. El saldo acumulado por periodo paga (o
    cobra, cuando el anticipo lo vuelve negativo) la tasa. No se interpola,
    no se estima: listas de la misma longitud o nada."""
    tasa_periodo = analisis.tasa_anual / 12.0 / 100.0
    periodos: list[PeriodoFinanciamiento] = []
    saldo = 0.0
    total = 0.0
    for numero, (egreso, ingreso) in enumerate(zip(egresos, ingresos, strict=True), start=1):
        saldo = round(saldo + egreso - ingreso, 2)
        costo = round(saldo * tasa_periodo, 2)
        total = round(total + costo, 2)
        periodos.append(PeriodoFinanciamiento(
            periodo=numero, egresos=round(egreso, 2), ingresos=round(ingreso, 2),
            saldo=saldo, costo=costo,
        ))
    return DocumentoFinanciamiento(
        tasa_anual=analisis.tasa_anual, indicador=analisis.indicador,
        fuente=analisis.fuente, fecha_publicacion=analisis.fecha_publicacion,
        periodos=periodos, total=total,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_indirectos.py -v`
Expected: 8 PASS

- [ ] **Step 5: Commit**

```bash
git add packages/klave_engine/costing/indirectos.py tests/test_indirectos.py
git commit -m "feat(costing): financiamiento del flujo — saldo por periodo a la tasa capturada, negativo cuando el anticipo financia

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Campos de configuración y el resolvedor

**Files:**
- Modify: `packages/klave_engine/costing/models.py` (imports; `IntegrationLine`; `CostingConfig`; `CostReport`)
- Modify: `packages/klave_engine/costing/integration.py` (add `resolve_integration`)
- Test: `tests/test_indirectos.py` (append)

**Interfaces:**
- Consumes: everything from Tasks 1–2; `build_personal_tecnico` from `plantilla.py`; `WorkSchedule`, `FinancialPlan`, `CostingConfig` from `models.py`.
- Produces:
  - `models.IntegrationLine` gains `fuente: str = "declarado"`
  - `models.CostingConfig` gains `desglose_campo: DesgloseCampo | None = None`, `financiamiento: AnalisisFinanciamiento | None = None`, `cargos_adicionales: list[CargoAdicional] = []`, `oficina_share_pct: float | None = None`, `oficina_share_motivo: str = ""`
  - `models.CostReport` gains `integracion_resuelta: list[ComponenteResuelto] = []`
  - `integration.resolve_integration(config: CostingConfig, integracion_taller: dict | None, direct_cost: float, schedule: WorkSchedule | None, flujo: FinancialPlan | None) -> list[ComponenteResuelto]` — always returns exactly five components in order CI-C, CI-O, FI, UT, CA.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_indirectos.py`)

```python
from klave_engine.costing.indirectos import CargoAdicional
from klave_engine.costing.integration import integrate_costs, resolve_integration
from klave_engine.costing.models import (
    CostingConfig,
    FinancialConfig,
    IndirectsConfig,
    ScheduleActivity,
    WorkSchedule,
)
from klave_engine.costing.financial import build_financial_plan
from klave_engine.costing.plantilla import CargoCampo


def _schedule(months: int = 2) -> WorkSchedule:
    days = months * 24
    return WorkSchedule(
        activities=[ScheduleActivity(
            concept_code="EST-001", description="Obra", phase="Estructura",
            quantity=1.0, unit="LOTE", rendimiento_per_day=1.0, crews=1,
            duration_days=days, start_day=0, end_day=days, direct_cost=1_000_000.0,
        )],
        total_duration_days=days, workdays_per_month=24, phases=["Estructura"],
    )


def test_resolver_todo_declarado_sin_captura():
    config = CostingConfig()
    resolved = resolve_integration(config, None, 1_000_000.0, _schedule(), None)
    assert [c.code for c in resolved] == ["CI-C", "CI-O", "FI", "UT", "CA"]
    assert all(c.fuente == "declarado" for c in resolved)
    assert all(c.amount is None for c in resolved)
    # Nada capturado = nada que reclamar: sin faltantes ruidosos.
    assert all(not c.faltantes for c in resolved)
    assert resolved[0].pct == IndirectsConfig().field_indirects_pct


def test_resolver_campo_con_desglose_y_plantilla():
    config = CostingConfig()
    config.desglose_campo = DesgloseCampo(rubros=[
        RubroIndirecto(concepto="Renta de bodega", importe=10_000.0, base="mensual"),
    ])
    config.plantilla_campo = [CargoCampo(puesto="Residente de obra", salario_mensual=30_000.0, fsr=1.6)]
    resolved = resolve_integration(config, None, 1_000_000.0, _schedule(months=2), None)
    campo = resolved[0]
    # 10,000×2 + (30,000×1.6×2) = 20,000 + 96,000 = 116,000
    assert campo.fuente == "analisis" and campo.amount == 116_000.0
    assert campo.documento["por_periodo"] == [58_000.0, 58_000.0]


def test_resolver_oficina_parcial_reclama_el_volumen():
    config = CostingConfig()
    taller = {"oficina": {"rubros": [{"concepto": "Renta", "importe": 600_000.0}],
                          "volumen_anual_contratado": 0.0}}
    resolved = resolve_integration(config, taller, 1_000_000.0, _schedule(), None)
    oficina = resolved[1]
    assert oficina.fuente == "declarado"
    assert any("volumen anual" in f for f in oficina.faltantes)


def test_resolver_financiamiento_necesita_tasa_y_flujo():
    config = CostingConfig()
    config.financiamiento = AnalisisFinanciamiento(tasa_anual=12.0, indicador="TIIE 28 días")
    sched = _schedule()
    sin_flujo = resolve_integration(config, None, 1_000_000.0, sched, None)
    assert sin_flujo[2].fuente == "declarado"
    assert any("fuente" in f for f in sin_flujo[2].faltantes)  # análisis parcial: se reclama
    config.financiamiento = AnalisisFinanciamiento(
        tasa_anual=12.0, indicador="TIIE 28 días",
        fuente="Banxico SF43783", fecha_publicacion="2026-08-27")
    integration = integrate_costs(1_000_000.0, config.indirects)
    flujo = build_financial_plan(sched, integration, FinancialConfig())
    con_flujo = resolve_integration(config, None, 1_000_000.0, sched, flujo)
    fi = con_flujo[2]
    assert fi.fuente == "analisis" and fi.amount is not None
    assert fi.documento["periodos"], "el documento trae la tabla por periodo"


def test_resolver_cargos_itemizados():
    config = CostingConfig()
    config.cargos_adicionales = [
        CargoAdicional(concepto="Inspección y vigilancia", base_legal="5 al millar", pct=0.5),
        CargoAdicional(concepto="Impuesto estatal de obra", base_legal="2 al millar", pct=0.2),
    ]
    resolved = resolve_integration(config, None, 1_000_000.0, _schedule(), None)
    ca = resolved[4]
    assert ca.fuente == "analisis" and ca.amount is None and ca.pct == 0.7
    assert len(ca.documento["items"]) == 2


def test_utilidad_siempre_declarada():
    config = CostingConfig()
    resolved = resolve_integration(config, None, 1_000_000.0, _schedule(), None)
    assert resolved[3].code == "UT" and resolved[3].fuente == "declarado"


def test_share_de_oficina_solo_con_motivo_escrito():
    taller = {"oficina": {"rubros": [{"concepto": "Renta", "importe": 600_000.0}],
                          "volumen_anual_contratado": 40_000_000.0}}
    config = CostingConfig()
    config.oficina_share_pct = 3.0
    config.oficina_share_motivo = "corto"  # < 15 caracteres: no cuenta
    resolved = resolve_integration(config, taller, 1_000_000.0, _schedule(), None)
    oficina = resolved[1]
    assert oficina.amount == 15_000.0  # 1.5 % derivado del prorrateo, no el 3 %
    assert any("motivo" in f for f in oficina.faltantes)

    config.oficina_share_motivo = "obra fuera de la zona de cobertura de la oficina"
    resolved = resolve_integration(config, taller, 1_000_000.0, _schedule(), None)
    oficina = resolved[1]
    assert oficina.amount == 30_000.0 and oficina.fuente == "analisis"
    assert oficina.documento["override"] == 3.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_indirectos.py -v -k resolver`
Expected: FAIL — `ImportError: cannot import name 'resolve_integration'`

- [ ] **Step 3: Modify `models.py`**

Add to the imports at the top (models.py already imports from `plantilla`; mirror that placement):

```python
from klave_engine.costing.indirectos import (
    AnalisisFinanciamiento,
    CargoAdicional,
    ComponenteResuelto,
    DesgloseCampo,
)
```

In `IntegrationLine` add one field at the end:

```python
    # De dónde salió este renglón: "analisis" (un documento lo respalda) o
    # "declarado" (porcentaje del taller, sin análisis detrás).
    fuente: str = "declarado"
```

In `CostingConfig`, after `plantilla_campo`:

```python
    # Integración como análisis (modo dual): capturados = el importe manda;
    # None/vacío = el porcentaje declarado de ``indirects`` con su etiqueta.
    desglose_campo: DesgloseCampo | None = None
    financiamiento: AnalisisFinanciamiento | None = None
    cargos_adicionales: list[CargoAdicional] = Field(default_factory=list)
    # Share de oficina central fijado a mano: sólo vale con motivo escrito
    # (≥15 caracteres), y queda como criterio, no como alarma.
    oficina_share_pct: float | None = None
    oficina_share_motivo: str = ""
```

In `CostReport`, after `indirectos_campo`:

```python
    # La integración con sus fuentes por componente y los documentos que los
    # exports imprimen tal cual (jamás recalculan).
    integracion_resuelta: list[ComponenteResuelto] = Field(default_factory=list)
```

- [ ] **Step 4: Add `resolve_integration` to `integration.py`**

Replace the module imports and append the resolver (keep `integrate_costs` as-is for now — Task 4 touches it):

```python
import math

from klave_engine.costing.indirectos import (
    AnalisisFinanciamiento,
    ComponenteResuelto,
    DesgloseOficinaCentral,
    compute_financiamiento,
    documenta_campo,
    documenta_oficina,
)
from klave_engine.costing.models import (
    CostIntegration,
    CostingConfig,
    FinancialPlan,
    IndirectsConfig,
    IntegrationLine,
    WorkSchedule,
)
from klave_engine.costing.plantilla import build_personal_tecnico


def resolve_integration(
    config: CostingConfig,
    integracion_taller: dict | None,
    direct_cost: float,
    schedule: WorkSchedule | None,
    flujo: FinancialPlan | None,
) -> list[ComponenteResuelto]:
    """Cada componente con su fuente dicha: análisis cuando los datos alcanzan,
    porcentaje declarado cuando no — y en ese caso, qué falta exactamente.

    Los faltantes se reclaman sólo cuando alguien capturó a medias: un taller
    que no ha capturado nada trabaja en modo declarado sin regaños, igual que
    la plantilla no alarma cuando no existe."""
    taller = integracion_taller or {}
    ind = config.indirects
    out: list[ComponenteResuelto] = []

    # ---- CI de campo -------------------------------------------------
    if config.desglose_campo is not None and schedule is not None:
        period_days = schedule.workdays_per_month or 24
        meses = (
            max(1, math.ceil(schedule.total_duration_days / period_days))
            if schedule.total_duration_days else 1
        )
        programa = build_personal_tecnico(config.plantilla_campo, meses, period_days, "mes")
        doc = documenta_campo(
            config.desglose_campo, meses, programa.total, programa.cargos_sin_sueldo
        )
        mensual_mes = sum(
            r.importe for r in config.desglose_campo.rubros
            if r.base == "mensual" and r.importe > 0
        )
        unicos = sum(
            r.importe for r in config.desglose_campo.rubros
            if r.base == "unico" and r.importe > 0
        )
        por_periodo = []
        for i in range(meses):
            plantilla_i = (
                programa.total_por_periodo[i]
                if i < len(programa.total_por_periodo) else 0.0
            )
            por_periodo.append(round(
                mensual_mes + plantilla_i + (unicos if i == 0 else 0.0), 2
            ))
        documento = doc.model_dump()
        documento["por_periodo"] = por_periodo
        faltantes = [n for n in doc.notas if "sin importe" in n or "sin sueldo" in n]
        out.append(ComponenteResuelto(
            code="CI-C", amount=doc.total, fuente="analisis",
            documento=documento, faltantes=faltantes,
        ))
    else:
        out.append(ComponenteResuelto(code="CI-C", pct=ind.field_indirects_pct))

    # ---- CI de oficina central ---------------------------------------
    oficina = DesgloseOficinaCentral.model_validate(taller.get("oficina") or {})
    doc_oficina = documenta_oficina(oficina, direct_cost)
    if doc_oficina is not None:
        documento_oficina = doc_oficina.model_dump()
        importe_oficina = doc_oficina.total
        faltantes_oficina: list[str] = []
        if config.oficina_share_pct is not None:
            if len(config.oficina_share_motivo.strip()) >= 15:
                importe_oficina = round(direct_cost * config.oficina_share_pct / 100.0, 2)
                documento_oficina["override"] = config.oficina_share_pct
                documento_oficina["motivo"] = config.oficina_share_motivo.strip()
                documento_oficina.setdefault("notas", []).append(
                    f"Share fijado a mano en {config.oficina_share_pct:g} % — "
                    f"{config.oficina_share_motivo.strip()}"
                )
            else:
                faltantes_oficina = [
                    "share de oficina fijado sin motivo escrito (≥15 caracteres): "
                    "se usa el prorrateo derivado"
                ]
        out.append(ComponenteResuelto(
            code="CI-O", amount=importe_oficina, fuente="analisis",
            documento=documento_oficina, faltantes=faltantes_oficina,
        ))
    else:
        faltantes = []
        if oficina.rubros:  # capturó rubros pero no el volumen: eso sí se reclama
            faltantes = ["sin volumen anual contratado: el prorrateo de oficina "
                         "central no puede calcularse"]
        out.append(ComponenteResuelto(
            code="CI-O", pct=ind.office_indirects_pct, faltantes=faltantes,
        ))

    # ---- Financiamiento ----------------------------------------------
    analisis = config.financiamiento
    if analisis is None and taller.get("financiamiento"):
        analisis = AnalisisFinanciamiento.model_validate(taller["financiamiento"])
    if analisis is not None and analisis.completo and flujo is not None and flujo.periods:
        n = len(flujo.periods)
        campo = out[0]
        campo_total = (
            campo.amount if campo.amount is not None
            else round(direct_cost * campo.pct / 100.0, 2)
        )
        oficina_total = (
            out[1].amount if out[1].amount is not None
            else round(direct_cost * out[1].pct / 100.0, 2)
        )
        campo_pp = list(campo.documento.get("por_periodo") or [])
        if not campo_pp:
            campo_pp = [round(campo_total / n, 2)] * n
        if len(campo_pp) < n:
            campo_pp += [0.0] * (n - len(campo_pp))
        total_spend = sum(p.direct_spend for p in flujo.periods) or 1.0
        egresos = [
            p.direct_spend + campo_pp[i] + oficina_total * (p.direct_spend / total_spend)
            for i, p in enumerate(flujo.periods)
        ]
        ingresos = [p.net_cashflow for p in flujo.periods]
        doc_fi = compute_financiamiento(analisis, egresos, ingresos)
        out.append(ComponenteResuelto(
            code="FI", amount=doc_fi.total, fuente="analisis",
            documento=doc_fi.model_dump(),
        ))
    else:
        faltantes = []
        if analisis is not None and analisis.faltantes():
            faltantes = [f"sin {f} capturada" if f == "tasa" else f"sin {f}"
                         for f in analisis.faltantes()]
        out.append(ComponenteResuelto(
            code="FI", pct=ind.financing_pct, faltantes=faltantes,
        ))

    # ---- Utilidad: declarada por diseño ------------------------------
    out.append(ComponenteResuelto(code="UT", pct=ind.profit_pct))

    # ---- Cargos adicionales ------------------------------------------
    if config.cargos_adicionales:
        out.append(ComponenteResuelto(
            code="CA", fuente="analisis",
            pct=round(sum(c.pct for c in config.cargos_adicionales), 6),
            documento={"items": [c.model_dump() for c in config.cargos_adicionales]},
        ))
    else:
        out.append(ComponenteResuelto(code="CA", pct=ind.additional_charges_pct))

    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_indirectos.py -v`
Expected: all PASS

- [ ] **Step 6: Run the neighbors to catch model fallout**

Run: `pytest tests/test_plantilla.py tests/test_obra_api.py tests/test_gold_money.py -q`
Expected: PASS (new fields all have defaults; old artifacts still validate)

- [ ] **Step 7: Commit**

```bash
git add packages/klave_engine/costing/models.py packages/klave_engine/costing/integration.py tests/test_indirectos.py
git commit -m "feat(costing): resolvedor de la integracion — cada componente con su fuente y sus faltantes dichos

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `integrate_costs` con importes primero

**Files:**
- Modify: `packages/klave_engine/costing/integration.py` (the `integrate_costs` function)
- Test: `tests/test_indirectos.py` (append)

**Interfaces:**
- Produces: `integrate_costs(direct_cost: float, config: IndirectsConfig, resolved: list[ComponenteResuelto] | None = None) -> CostIntegration`. With `resolved=None` behavior is IDENTICAL to today. With amounts, `IntegrationLine.percentage` = `round(amount / base * 100.0, 4)` and `IntegrationLine.fuente` mirrors the component.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_indirectos.py`)

```python
from klave_engine.costing.indirectos import ComponenteResuelto


def test_integrate_declarado_identico_a_hoy():
    # La garantía de regresión del modo dual: sin resolved, la aritmética de
    # siempre (los importes encadenados, verificados a mano para el primero).
    config = IndirectsConfig()
    antes = integrate_costs(1_000_000.0, config)
    despues = integrate_costs(1_000_000.0, config, resolved=None)
    assert antes.model_dump() == despues.model_dump()
    assert [l.code for l in antes.lines] == ["CI-C", "CI-O", "FI", "UT", "CA"]
    assert antes.lines[0].amount == 80_000.0  # 8 % de 1,000,000, a mano
    assert antes.lines[2].base == 1_130_000.0  # FI corre sobre CD+CI
    assert all(line.fuente == "declarado" for line in antes.lines)


def test_integrate_amounts_mandan_y_el_pct_es_derivado():
    config = IndirectsConfig()
    resolved = [
        ComponenteResuelto(code="CI-C", amount=116_000.0, fuente="analisis"),
        ComponenteResuelto(code="CI-O", pct=5.0),
        ComponenteResuelto(code="FI", pct=1.5),
        ComponenteResuelto(code="UT", pct=10.0),
        ComponenteResuelto(code="CA", pct=0.5),
    ]
    integration = integrate_costs(1_000_000.0, config, resolved=resolved)
    campo = integration.lines[0]
    assert campo.amount == 116_000.0 and campo.fuente == "analisis"
    assert campo.percentage == 11.6  # derivado del importe, no al revés
    # El documento y el presupuesto no pueden discrepar ni por un centavo:
    assert campo.amount == round(1_000_000.0 * campo.percentage / 100.0, 2)


def test_integrate_pct_resuelto_reemplaza_al_de_config():
    config = IndirectsConfig()  # additional_charges_pct = 0.5
    resolved = resolve_integration(CostingConfig(), None, 1_000_000.0, _schedule(), None)
    resolved[4] = ComponenteResuelto(code="CA", pct=0.7, fuente="analisis")
    integration = integrate_costs(1_000_000.0, config, resolved=resolved)
    ca = integration.lines[4]
    assert ca.percentage == 0.7 and ca.fuente == "analisis"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_indirectos.py -v -k integrate`
Expected: FAIL — `TypeError: integrate_costs() got an unexpected keyword argument 'resolved'`

- [ ] **Step 3: Rewrite `integrate_costs`**

Replace the whole function body (docstring of the module stays):

```python
def integrate_costs(
    direct_cost: float,
    config: IndirectsConfig,
    resolved: list[ComponenteResuelto] | None = None,
) -> CostIntegration:
    componentes = {c.code: c for c in (resolved or [])}
    lines: list[IntegrationLine] = []
    accumulated = direct_cost

    def add(code: str, description: str, base: float, pct: float) -> float:
        nonlocal accumulated
        comp = componentes.get(code)
        fuente = comp.fuente if comp is not None else "declarado"
        if comp is not None and comp.amount is not None:
            # El importe del análisis manda; el porcentaje es su sombra.
            amount = round(comp.amount, 2)
            pct = round(amount / base * 100.0, 4) if base else 0.0
        else:
            if comp is not None:
                pct = comp.pct
            amount = round(base * pct / 100.0, 2)
        accumulated = round(accumulated + amount, 2)
        lines.append(
            IntegrationLine(
                code=code,
                description=description,
                base=round(base, 2),
                percentage=pct,
                amount=amount,
                accumulated=accumulated,
                fuente=fuente,
            )
        )
        return amount

    # Campo y oficina central van en renglones separados porque se revisan por
    # separado: el de campo es el que tiene que cuadrar contra la plantilla de
    # personal del programa del art. 45-A-XI-d.
    add("CI-C", "Costos indirectos de campo", direct_cost, config.field_indirects_pct)
    add(
        "CI-O",
        "Costos indirectos de oficina central",
        direct_cost,
        config.office_indirects_pct,
    )
    add("FI", "Costo de financiamiento", accumulated, config.financing_pct)
    add("UT", "Utilidad", accumulated, config.profit_pct)
    add("CA", "Cargos adicionales", accumulated, config.additional_charges_pct)

    sale_price = accumulated
    contingency = round(sale_price * config.contingency_pct / 100.0, 2)
    return CostIntegration(
        direct_cost=round(direct_cost, 2),
        lines=lines,
        sale_price=sale_price,
        contingency=contingency,
        grand_total=round(sale_price + contingency, 2),
        overcost_factor=round(sale_price / direct_cost, 4) if direct_cost else 0.0,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_indirectos.py -v`
Expected: all PASS

- [ ] **Step 5: Regression sweep**

Run: `pytest tests/test_gold_money.py tests/test_obra_api.py tests/test_exports.py tests/test_programas.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add packages/klave_engine/costing/integration.py tests/test_indirectos.py
git commit -m "feat(costing): integrate_costs con importes primero — el analisis manda y el porcentaje es derivado

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: El reporte itera integración y flujo

**Files:**
- Modify: `packages/klave_engine/costing/report.py` (signature + the block at ~lines 336–350 + `_warn_plantilla_vs_indirectos` call + `CostReport(...)` construction)
- Modify: `packages/klave_engine/pipeline.py:605` (call site)
- Modify: `packages/klave_engine/costing/recompute.py:116` (call site)
- Test: `tests/test_indirectos.py` (append)

**Interfaces:**
- Consumes: `resolve_integration`, `integrate_costs(…, resolved=…)`, `build_financial_plan`.
- Produces:
  - `generate_cost_report(..., integracion_taller: dict | None = None)` — new last keyword parameter.
  - `report._integrate_with_analyses(direct_cost: float, config: CostingConfig, integracion_taller: dict | None, schedule: WorkSchedule, currency: str, warnings: list[str]) -> tuple[list[ComponenteResuelto], CostIntegration, FinancialPlan]` — the extracted, testable loop.
  - `CostReport.integracion_resuelta` populated; `CostReport.indirectos_campo` = the CI-C line's `amount` (identical value to today in declared mode).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_indirectos.py`)

```python
from klave_engine.costing.report import _integrate_with_analyses


def _config_analisis_total() -> CostingConfig:
    config = CostingConfig()
    config.desglose_campo = DesgloseCampo(rubros=[
        RubroIndirecto(concepto="Renta de bodega", importe=10_000.0, base="mensual")])
    config.plantilla_campo = [CargoCampo(puesto="Residente de obra",
                                         salario_mensual=30_000.0, fsr=1.6)]
    config.financiamiento = AnalisisFinanciamiento(
        tasa_anual=12.0, indicador="TIIE 28 días",
        fuente="Banxico SF43783", fecha_publicacion="2026-08-27")
    return config


def test_iteracion_converge_y_los_totales_se_estabilizan():
    warnings: list[str] = []
    resolved, integration, financial = _integrate_with_analyses(
        1_000_000.0, _config_analisis_total(), None, _schedule(months=2), "MXN", warnings)
    fi = next(c for c in resolved if c.code == "FI")
    assert fi.fuente == "analisis"
    # Punto fijo: reintegrar con lo resuelto no mueve el total ni un centavo.
    again = integrate_costs(1_000_000.0, _config_analisis_total().indirects, resolved=resolved)
    assert abs(again.grand_total - integration.grand_total) < 0.01
    assert not any("no convergió" in w for w in warnings)


def test_modo_declarado_una_pasada_numeros_de_siempre():
    warnings: list[str] = []
    resolved, integration, _ = _integrate_with_analyses(
        1_000_000.0, CostingConfig(), None, _schedule(), "MXN", warnings)
    assert all(c.fuente == "declarado" for c in resolved)
    assert integration.model_dump(exclude={"lines"}) == integrate_costs(
        1_000_000.0, IndirectsConfig()).model_dump(exclude={"lines"})
    assert warnings == []


def test_faltantes_parciales_llegan_como_warnings():
    config = CostingConfig()
    config.financiamiento = AnalisisFinanciamiento(tasa_anual=12.0)  # a medias
    warnings: list[str] = []
    _integrate_with_analyses(1_000_000.0, config, None, _schedule(), "MXN", warnings)
    assert any("Integración (FI)" in w and "sin indicador" in w for w in warnings)


def test_congruencia_de_plantilla_solo_en_modo_declarado():
    from klave_engine.costing.models import BillOfQuantities
    from klave_engine.costing.report import _warn_plantilla_vs_indirectos

    config = CostingConfig()
    config.plantilla_campo = [CargoCampo(puesto="Residente de obra",
                                         salario_mensual=80_000.0, fsr=1.6)]
    sched = _schedule(months=2)
    # Plantilla 256,000 contra indirectos de campo de 100,000: desajuste real.
    declarado = BillOfQuantities(project_id="p")
    _warn_plantilla_vs_indirectos(declarado, config, sched, 100_000.0,
                                  ci_c_fuente="declarado")
    assert any("plantilla" in w for w in declarado.warnings)
    # En modo análisis la plantilla está DENTRO del desglose: comparar sería
    # compararla consigo misma, y el aviso no existe.
    analisis = BillOfQuantities(project_id="p")
    _warn_plantilla_vs_indirectos(analisis, config, sched, 100_000.0,
                                  ci_c_fuente="analisis")
    assert analisis.warnings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_indirectos.py -v -k "iteracion or declarado_una or faltantes_parciales"`
Expected: FAIL — `ImportError: cannot import name '_integrate_with_analyses'`

- [ ] **Step 3: Implement in `report.py`**

Add the imports (`resolve_integration` from integration; `ComponenteResuelto` comes via models). Add the helper above `generate_cost_report`:

```python
def _integrate_with_analyses(
    direct_cost: float,
    config: CostingConfig,
    integracion_taller: dict | None,
    schedule: WorkSchedule,
    currency: str,
    warnings: list[str],
) -> tuple[list[ComponenteResuelto], CostIntegration, FinancialPlan]:
    """Integración y flujo al punto fijo.

    Sólo el financiamiento depende del flujo, y el flujo del precio de venta:
    se siembra con lo declarado y se itera. El factor de perturbación es la
    porción del financiamiento (~1–3 %), así que converge en pocas pasadas;
    el tope de 10 es un guardarraíl, y tocarlo se dice con el residual."""
    resolved = resolve_integration(config, integracion_taller, direct_cost, schedule, None)
    integration = integrate_costs(direct_cost, config.indirects, resolved=resolved)
    financial = build_financial_plan(schedule, integration, config.financial, currency)
    residual = 0.0
    for _ in range(10):
        resolved = resolve_integration(
            config, integracion_taller, direct_cost, schedule, financial
        )
        if next(c for c in resolved if c.code == "FI").fuente == "declarado":
            integration = integrate_costs(direct_cost, config.indirects, resolved=resolved)
            financial = build_financial_plan(schedule, integration, config.financial, currency)
            break
        new_integration = integrate_costs(direct_cost, config.indirects, resolved=resolved)
        new_financial = build_financial_plan(schedule, new_integration, config.financial, currency)
        residual = abs(new_integration.grand_total - integration.grand_total)
        integration, financial = new_integration, new_financial
        if residual < 0.01:
            break
    else:
        warnings.append(
            f"El costo de financiamiento no convergió tras 10 iteraciones; "
            f"residual de ${residual:,.2f} en el total con contingencia."
        )
    for comp in resolved:
        for falta in comp.faltantes:
            warnings.append(
                f"Integración ({comp.code}): {falta}. El componente sigue por "
                "porcentaje declarado."
            )
    if any(c.fuente == "analisis" for c in resolved):
        warnings.append(
            f"Utilidad declarada: {config.indirects.profit_pct:g} % — criterio "
            "del taller, no un análisis."
        )
    oficina = next(c for c in resolved if c.code == "CI-O")
    if oficina.documento.get("override") is not None:
        warnings.append(
            f"Oficina central por share fijado: {oficina.documento['override']:g} % — "
            f"{oficina.documento.get('motivo', '')}"
        )
    return resolved, integration, financial
```

Note the faltantes loop: a *declared* component reports its faltantes too (that is the partial-capture reclaim — `resolve_integration` only fills `faltantes` on partial capture). But when the component is "analisis" its faltantes (rubros sin importe, cargos sin sueldo) also surface. Both are wanted.

Then in `generate_cost_report`:
1. Add the parameter `integracion_taller: dict | None = None` at the end of the signature.
2. Replace the current block (integration at ~line 336, `indirectos_campo` computation, and the `financial = build_financial_plan(...)` at ~line 348) with — keeping `schedule = build_schedule(...)` where it is and moving integration AFTER it:

```python
    schedule = build_schedule(boq, catalog, config.schedule, levels=levels, apus=apus)
    resolved, integration, financial = _integrate_with_analyses(
        boq.direct_cost_total, config, integracion_taller, schedule,
        config.currency, boq.warnings,
    )
    indirectos_campo = next(l.amount for l in integration.lines if l.code == "CI-C")
```

(The `levels = (...)` computation currently sits between integration and schedule; keep it before `build_schedule` — only the integration lines move below the schedule.)

3. Guard the congruence warning — `_warn_plantilla_vs_indirectos` gains a final parameter `ci_c_fuente: str = "declarado"` and returns immediately when it is `"analisis"` (add one line at the top of the function body, before the plantilla check, with the comment: `# En modo análisis la plantilla está dentro del desglose: no hay dos números que comparar.`). The call site becomes:

```python
    _warn_plantilla_vs_indirectos(
        boq, config, schedule, indirectos_campo,
        ci_c_fuente=next(c for c in resolved if c.code == "CI-C").fuente,
    )
```

4. In the `CostReport(...)` construction add `integracion_resuelta=resolved,`.

- [ ] **Step 4: Wire the two call sites**

`packages/klave_engine/pipeline.py` (~line 605 call): add argument
`integracion_taller=catalog_store.get_setting("integracion"),`

`packages/klave_engine/costing/recompute.py` (~line 116 call): add argument
`integracion_taller=store.get_setting("integracion"),`

(`evals/gold.py` stays untouched: default `None` = declared mode = gold money can't move.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_indirectos.py -v`
Expected: all PASS

- [ ] **Step 6: Full regression sweep**

Run: `pytest tests/test_gold_money.py tests/test_gold.py tests/test_obra_api.py tests/test_exports.py tests/test_programas.py tests/test_plantilla.py tests/test_estimaciones.py -q`
Expected: PASS. `indirectos_campo` in declared mode is `round(direct × pct / 100, 2)` exactly as before (same arithmetic, now read off the CI-C line).

- [ ] **Step 7: Commit**

```bash
git add packages/klave_engine/costing/report.py packages/klave_engine/pipeline.py packages/klave_engine/costing/recompute.py tests/test_indirectos.py
git commit -m "feat(costing): el reporte itera integracion y flujo al punto fijo — modo declarado en una pasada, identico a hoy

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Hallazgos y criterios de la integración

**Files:**
- Modify: `packages/klave_engine/costing/hallazgos.py` (`_RULES` list)
- Test: `tests/test_hallazgos.py` (append)

**Interfaces:**
- Consumes: the exact warning strings emitted by `_integrate_with_analyses` in Task 5.
- Produces: three new `Rule` entries; no new severity vocabulary.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_hallazgos.py`, following that file's existing conventions for building a minimal report — read its helpers first and reuse them)

```python
def test_integracion_incompleta_es_revisar_y_se_agrupa():
    from klave_engine.costing.hallazgos import _classify

    rule = _classify(
        "Integración (FI): sin indicador. El componente sigue por porcentaje declarado."
    )
    assert rule.severity == "revisar" and rule.group == "integracion_incompleta"


def test_utilidad_declarada_es_criterio_no_alarma():
    from klave_engine.costing.hallazgos import _classify

    rule = _classify("Utilidad declarada: 10 % — criterio del taller, no un análisis.")
    assert rule.criterio is True


def test_no_convergencia_es_dinero():
    from klave_engine.costing.hallazgos import _classify

    rule = _classify(
        "El costo de financiamiento no convergió tras 10 iteraciones; "
        "residual de $532.10 en el total con contingencia."
    )
    assert rule.severity == "dinero"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_hallazgos.py -v -k "integracion or utilidad_declarada or convergencia"`
Expected: FAIL — the strings fall through to `_FALLBACK` (severity "revisar" but empty group), so the group/criterio asserts fail.

- [ ] **Step 3: Add the rules to `_RULES`**

Insert before the `_FALLBACK` definition, mirroring the style of the neighbors (see the `criterio=True` examples around lines 276–286):

```python
    Rule(
        pattern=r"Integración \((CI-C|CI-O|FI|CA)\): ",
        severity="revisar",
        action="Completa la captura para que el análisis sustituya al porcentaje declarado.",
        target="parametros",
        group="integracion_incompleta",
        plural="{n} componentes de la integración siguen por porcentaje declarado",
        momento="cotizar",
        verificar="Revisa Integración en parámetros del proyecto y en el catálogo del taller.",
    ),
    Rule(
        pattern=r"Utilidad declarada: ",
        severity="revisar",
        criterio=True,
    ),
    Rule(
        pattern=r"costo de financiamiento no convergió",
        severity="dinero",
        action="Revisa tasa y calendario del flujo; el residual indica cuánto baila el total.",
        target="parametros",
        momento="entregar",
        verificar="Compara el total de dos recomputos seguidos.",
    ),
    Rule(
        pattern=r"Oficina central por share fijado",
        severity="revisar",
        criterio=True,
    ),
```

And one more test alongside the others:

```python
def test_share_fijado_es_criterio():
    from klave_engine.costing.hallazgos import _classify

    rule = _classify(
        "Oficina central por share fijado: 3 % — obra fuera de la zona de "
        "cobertura de la oficina"
    )
    assert rule.criterio is True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_hallazgos.py -q`
Expected: PASS (the whole file, not only the new tests — the new patterns must not shadow existing rules; if an existing test breaks, the new rules are matching too broadly and need tightening, not the old test changing).

- [ ] **Step 5: Commit**

```bash
git add packages/klave_engine/costing/hallazgos.py tests/test_hallazgos.py
git commit -m "feat(hallazgos): la integracion incompleta se agrupa, la utilidad declarada es criterio y la no-convergencia es dinero

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: API — captura del taller y fuentes en la configuración

**Files:**
- Modify: `apps/api/routes/catalog.py` (new routes near `/indices`)
- Modify: `apps/api/routes/reports.py` (`get_costing_config` response)
- Test: `tests/test_indirectos_api.py` (create)

**Interfaces:**
- Consumes: `CatalogStore.get_setting/set_setting` (exist), `require_catalog_admin`, `_publish_catalog_updated` (exist in catalog.py — read their usage at the `/indices` routes and mirror it exactly).
- Produces:
  - `GET /catalog/integracion` → `{"oficina": {...}, "financiamiento": {...}}` (empty dicts when unset)
  - `PUT /catalog/integracion` body `{"oficina": {...}, "financiamiento": {...}}` — validated through `DesgloseOficinaCentral` / `AnalisisFinanciamiento`, stored under settings key `"integracion"`, audit event `"integracion_saved"`.
  - `GET /projects/{id}/costing-config` response gains `"integracion": [{"code","pct","amount","fuente","faltantes"}]` read from the stored `cost_report.json` (best-effort: `[]` when no report yet).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_indirectos_api.py`:

```python
"""La captura del taller (oficina central + financiamiento) por la API."""

from klave_engine.common import config as config_module


def _client(monkeypatch):
    from fastapi.testclient import TestClient

    from apps.api.main import create_app

    monkeypatch.setenv("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")
    config_module.get_settings.cache_clear()
    return TestClient(create_app())


def test_integracion_roundtrip(data_dir, monkeypatch):
    client = _client(monkeypatch)
    vacio = client.get("/catalog/integracion").json()
    assert vacio == {"oficina": {}, "financiamiento": {}}

    body = {
        "oficina": {
            "rubros": [{"concepto": "Renta de oficina", "categoria": "gastos_oficina",
                        "importe": 600000.0}],
            "volumen_anual_contratado": 40000000.0,
        },
        "financiamiento": {
            "tasa_anual": 12.0, "indicador": "TIIE 28 días",
            "fuente": "Banxico SF43783", "fecha_publicacion": "2026-08-27",
        },
    }
    saved = client.put("/catalog/integracion", json=body)
    assert saved.status_code == 200, saved.text
    stored = client.get("/catalog/integracion").json()
    assert stored["oficina"]["volumen_anual_contratado"] == 40000000.0
    assert stored["financiamiento"]["indicador"] == "TIIE 28 días"


def test_integracion_rechaza_basura(data_dir, monkeypatch):
    client = _client(monkeypatch)
    malo = client.put("/catalog/integracion", json={
        "oficina": {"volumen_anual_contratado": "mucho"}, "financiamiento": {}})
    assert malo.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_indirectos_api.py -v`
Expected: FAIL — 404 on `/catalog/integracion`

- [ ] **Step 3: Add the routes** (in `apps/api/routes/catalog.py`, next to the `/indices` block; reuse its imports)

```python
class IntegracionInput(BaseModel):
    oficina: dict = Field(default_factory=dict)
    financiamiento: dict = Field(default_factory=dict)


@router.get("/integracion")
def get_integracion(catalog: CatalogStore = Depends(get_catalog)) -> dict:
    stored = catalog.get_setting("integracion") or {}
    return {"oficina": stored.get("oficina") or {},
            "financiamiento": stored.get("financiamiento") or {}}


@router.put("/integracion")
def put_integracion(
    request: Request,
    body: IntegracionInput,
    x_actor: Annotated[str | None, Header()] = None,
    catalog: CatalogStore = Depends(get_catalog),
) -> dict:
    require_catalog_admin(request)
    try:
        oficina = DesgloseOficinaCentral.model_validate(body.oficina or {})
        financiamiento = AnalisisFinanciamiento.model_validate(body.financiamiento or {})
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail={
            "error_type": "integracion_invalida", "message": str(exc)[:400]}) from exc
    value = {"oficina": oficina.model_dump(), "financiamiento": financiamiento.model_dump()}
    catalog.set_setting("integracion", value)
    _publish_catalog_updated(
        x_actor, "integracion_saved",
        f"{len(oficina.rubros)} rubros de oficina", catalog=catalog,
    )
    return value
```

Add to the file's imports: `from klave_engine.costing.indirectos import AnalisisFinanciamiento, DesgloseOficinaCentral` and `from pydantic import ValidationError` (check what's already imported first).

- [ ] **Step 4: Extend `get_costing_config` in `apps/api/routes/reports.py`**

Read the function (line ~86) first. Add to its response dict:

```python
    integracion: list[dict] = []
    try:
        report = store.read_artifact(project_id, "cost_report.json")
        integracion = [
            {"code": c.get("code"), "pct": c.get("pct"), "amount": c.get("amount"),
             "fuente": c.get("fuente"), "faltantes": c.get("faltantes") or []}
            for c in report.get("integracion_resuelta") or []
        ]
    except HTTPException:
        pass  # sin reporte todavía: la forma muestra sólo lo declarado
```

and include `"integracion": integracion` in the returned payload.

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_indirectos_api.py tests/test_obra_api.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api/routes/catalog.py apps/api/routes/reports.py tests/test_indirectos_api.py
git commit -m "feat(api): captura de integracion del taller y fuentes por componente en la configuracion del proyecto

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: El guard de la licitación

**Files:**
- Modify: `apps/api/routes/exports.py` (`_guard_export` + `export_presupuesto`)
- Test: `tests/test_exports.py` (append)

**Interfaces:**
- Consumes: `CostReport.integracion_resuelta` (Task 3/5); the `_report(data_dir)` fixture style of `tests/test_exports.py` (reports built directly via `build_cost_report`, no API client — read the top of that file first and reuse its imports/helpers).
- Produces: `_licitacion_bloqueantes(report: CostReport) -> list[str]` in `apps/api/routes/exports.py` (pure, unit-tested), and `_guard_export(store, project_id, settings, motivo, extra_blocking: list[str] | None = None) -> str`. For `format` in `("licitacion", "licitacion_larga")`, each of CI-C/CI-O/FI/CA still in declared mode is a blocker; UT never is. An old artifact with empty `integracion_resuelta` blocks with a single "reprocesa" message.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_exports.py`; it builds reports directly with `build_cost_report` — reuse its `_report(data_dir)` and `_detections()` helpers and its imports)

```python
def test_licitacion_bloquea_componentes_declarados(data_dir):
    from apps.api.routes.exports import _licitacion_bloqueantes

    report, _ = _report(data_dir)  # modo declarado puro
    bloqueantes = _licitacion_bloqueantes(report)
    assert len(bloqueantes) == 4  # CI-C, CI-O, FI y CA; la utilidad no bloquea
    assert not any("(UT)" in b for b in bloqueantes)
    assert all("porcentaje declarado" in b for b in bloqueantes)


def test_licitacion_reporte_viejo_pide_reproceso(data_dir):
    from apps.api.routes.exports import _licitacion_bloqueantes

    report, _ = _report(data_dir)
    report.integracion_resuelta = []  # artefacto anterior a los análisis
    assert any("reprocesa" in b for b in _licitacion_bloqueantes(report))


def _overrides_analisis(data_dir):
    """Captura completa: campo, oficina del taller, tasa y cargos itemizados."""
    from klave_engine.costing.indirectos import (
        AnalisisFinanciamiento,
        CargoAdicional,
        DesgloseCampo,
        RubroIndirecto,
    )
    from klave_engine.costing.models import CostingOverrides

    get_catalog_store(data_dir).set_setting("integracion", {
        "oficina": {
            "rubros": [{"concepto": "Renta de oficina", "categoria": "gastos_oficina",
                        "importe": 600000.0}],
            "volumen_anual_contratado": 40000000.0,
        },
        "financiamiento": {"tasa_anual": 12.0, "indicador": "TIIE 28 días",
                           "fuente": "Banxico SF43783", "fecha_publicacion": "2026-08-27"},
    })
    overrides = CostingOverrides()
    overrides.config.desglose_campo = DesgloseCampo(rubros=[
        RubroIndirecto(concepto="Renta de bodega",
                       categoria="depreciacion_mantenimiento_rentas",
                       importe=10000.0, base="mensual")])
    overrides.config.cargos_adicionales = [CargoAdicional(
        concepto="Inspección y vigilancia", base_legal="5 al millar", pct=0.5)]
    return overrides


def test_licitacion_sin_bloqueantes_en_modo_analisis(data_dir):
    from apps.api.routes.exports import _licitacion_bloqueantes

    sembrar(get_catalog_store(data_dir))
    inputs = CostingInputs(
        project_id="p", detections=_detections(),
        units=DrawingUnits(unit="m", source="dxf_header", confidence=0.9),
        segmentation=None, dimensions=None,
    )
    report = build_cost_report(inputs, _overrides_analisis(data_dir))
    assert _licitacion_bloqueantes(report) == []
```

(If any of `CostingInputs`, `build_cost_report`, `sembrar`, `get_catalog_store`, `DrawingUnits` are not already imported at the top of `tests/test_exports.py`, they are — the `_report` fixture uses them. Do not re-import.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_exports.py -v -k licitacion`
Expected: FAIL — `ImportError: cannot import name '_licitacion_bloqueantes'`

- [ ] **Step 3: Implement**

In `apps/api/routes/exports.py`, add the pure function next to `_blocking_findings`:

```python
def _licitacion_bloqueantes(report: CostReport) -> list[str]:
    """El formato de licitación con un componente por porcentaje declarado es
    el documento desechable que este análisis existe para impedir. La utilidad
    declarada es un criterio de diseño y nunca bloquea."""
    resueltos = {c.code: c for c in report.integracion_resuelta}
    if not resueltos:
        return [
            "La integración no trae fuentes (reporte anterior a los análisis): "
            "reprocesa el proyecto."
        ]
    extra: list[str] = []
    for code, nombre in (
        ("CI-C", "indirectos de campo"), ("CI-O", "indirectos de oficina central"),
        ("FI", "financiamiento"), ("CA", "cargos adicionales"),
    ):
        comp = resueltos.get(code)
        if comp is not None and comp.fuente == "declarado":
            extra.append(
                f"El formato de licitación lleva {nombre} por porcentaje "
                f"declarado ({code}): sin análisis, es causal de desechamiento."
            )
    return extra
```

In `_guard_export`, add the parameter and merge:

```python
def _guard_export(
    store: ProjectStore, project_id: str, settings: Settings, motivo: str,
    extra_blocking: list[str] | None = None,
) -> str:
    blocking = _blocking_findings(store, project_id, settings) + list(extra_blocking or [])
```

(rest unchanged — the other export routes keep calling it without the new argument). In `export_presupuesto`, the guard currently runs before the report is read; move the `_guard_export` call to AFTER `report = CostReport.model_validate(...)` succeeds:

```python
    extra = (
        _licitacion_bloqueantes(report)
        if format in ("licitacion", "licitacion_larga") else []
    )
    reason = _guard_export(store, project_id, settings, motivo, extra_blocking=extra)
```

`_mark_exported` moves after the guard too (only a successful export marks). Keep the rate-limit call first.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_exports.py -q`
Expected: PASS (all — the reorder must not break the other export routes, which don't pass `extra_blocking`)

- [ ] **Step 5: Commit**

```bash
git add apps/api/routes/exports.py tests/test_exports.py
git commit -m "feat(exports): la licitacion rechaza componentes por porcentaje declarado — la utilidad declarada por diseno no bloquea

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Los documentos en el Excel

**Files:**
- Modify: `packages/klave_engine/costing/exports.py` (`_licitacion_workbook`; `_caratula`)
- Test: `tests/test_exports.py` (append)

**Interfaces:**
- Consumes: `report.integracion_resuelta` documentos (printed verbatim — the export layer NEVER recomputes), `CATEGORIA_LABEL` from `indirectos.py`, existing helpers `_title`, `_muted`, `_header` in exports.py (read their signatures first).
- Produces: licitación workbook gains sheets `"Análisis de indirectos"` and `"Financiamiento"` (the latter only when FI is analysis-backed); Carátula gains an "Integración del precio" block with fuente per line.

- [ ] **Step 1: Write the failing test** (append to `tests/test_exports.py`, direct-builder style like the rest of the file; `_overrides_analisis(data_dir)` was added to this same file by Task 8 — its body is repeated below in case that task's code moved)

```python
def test_licitacion_imprime_los_analisis(data_dir):
    from io import BytesIO

    from openpyxl import load_workbook

    sembrar(get_catalog_store(data_dir))
    inputs = CostingInputs(
        project_id="p", detections=_detections(),
        units=DrawingUnits(unit="m", source="dxf_header", confidence=0.9),
        segmentation=None, dimensions=None,
    )
    reviews = ProjectReviews()
    report = build_cost_report(inputs, _overrides_analisis(data_dir), reviews=reviews)
    contenido = build_presupuesto_workbook(
        report, _detections(), reviews,
        project_name="Obra de prueba", client="Cliente", fmt="licitacion",
    )
    libro = load_workbook(BytesIO(contenido))
    assert "Análisis de indirectos" in libro.sheetnames
    assert "Financiamiento" in libro.sheetnames
    indirectos = libro["Análisis de indirectos"]
    textos = [str(c.value) for fila in indirectos.iter_rows() for c in fila if c.value]
    assert any("Renta de bodega" in t for t in textos)
    assert any("volumen anual contratado" in t.lower() for t in textos)
    financiamiento = libro["Financiamiento"]
    ftextos = [str(c.value) for fila in financiamiento.iter_rows() for c in fila if c.value]
    assert any("TIIE 28 días" in t for t in ftextos)
    assert any("Banxico SF43783" in t for t in ftextos)
    # Los totales del documento y de la integración cuadran al centavo:
    campo = next(c for c in report.integracion_resuelta if c.code == "CI-C")
    linea = next(l for l in report.integration.lines if l.code == "CI-C")
    assert campo.amount == linea.amount


def test_caratula_dice_la_fuente_de_cada_renglon(data_dir):
    from io import BytesIO

    from openpyxl import load_workbook

    report, reviews = _report(data_dir)  # modo declarado
    contenido = build_presupuesto_workbook(
        report, _detections(), reviews,
        project_name="Obra de prueba", client=None, fmt="klave",
    )
    caratula = load_workbook(BytesIO(contenido))["Carátula"]
    textos = [str(c.value) for fila in caratula.iter_rows() for c in fila if c.value]
    assert any("declarado" in t for t in textos)
```

Mirror `build_presupuesto_workbook`'s exact call signature from `test_klave_workbook_structure_and_generadores` in the same file if it differs from the above. `_overrides_analisis` for reference: seeds `set_setting("integracion", {oficina: {rubros: [Renta de oficina 600000], volumen_anual_contratado: 40000000}, financiamiento: {tasa 12, TIIE 28 días, Banxico SF43783, 2026-08-27}})` and returns `CostingOverrides()` whose config carries a `desglose_campo` with "Renta de bodega" (10,000 mensual) and one `CargoAdicional` (0.5 %).

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_exports.py -v -k "imprime_los_analisis or caratula_dice"`
Expected: FAIL — sheet "Análisis de indirectos" not in sheetnames; no "declarado" text on the Carátula

- [ ] **Step 3: Implement the sheets**

In `exports.py`, two new sheet builders (place next to `_licitacion_workbook`, reuse `_title`/`_muted`/`_header` and the number formats used by `_flujo` — read `_flujo` first for the money-format idiom):

```python
def _analisis_indirectos(ws: Worksheet, report: CostReport) -> None:
    _title(ws, 1, "ANÁLISIS DE COSTOS INDIRECTOS", size=14)
    row = 3
    etiquetas = {"CI-C": "Indirectos de campo", "CI-O": "Indirectos de oficina central"}
    for comp in report.integracion_resuelta:
        if comp.code not in etiquetas:
            continue
        _muted(ws, row, 1, etiquetas[comp.code] + (
            "" if comp.fuente == "analisis" else " — PORCENTAJE DECLARADO, SIN ANÁLISIS"))
        row += 1
        doc = comp.documento or {}
        if doc.get("renglones"):
            _header(ws, row, ["Concepto", "Categoría", "Base", "Importe"])
            row += 1
            for renglon in doc["renglones"]:
                ws.cell(row=row, column=1, value=renglon["concepto"] + (
                    " (SIN CAPTURAR)" if renglon.get("sin_capturar") else ""))
                ws.cell(row=row, column=2,
                        value=CATEGORIA_LABEL.get(renglon["categoria"], renglon["categoria"]))
                ws.cell(row=row, column=3, value=renglon["base"])
                if not renglon.get("sin_capturar"):
                    ws.cell(row=row, column=4, value=renglon["importe"]).number_format = MONEY
                if renglon.get("fuente") == "plantilla de campo":
                    ws.cell(row=row, column=5, value="de la plantilla de campo")
                row += 1
            total = ws.cell(row=row, column=1, value="Total")
            total.font = Font(bold=True, size=9)
            ws.cell(row=row, column=4, value=doc.get("total", 0.0)).number_format = MONEY
            row += 1
        for nota in doc.get("notas", []):
            _muted(ws, row, 1, nota)
            row += 1
        row += 1
    ca = next((c for c in report.integracion_resuelta if c.code == "CA"), None)
    if ca is not None and ca.documento.get("items"):
        _muted(ws, row, 1, "Cargos adicionales")
        row += 1
        _header(ws, row, ["Concepto", "Base legal", "%"])
        row += 1
        for item in ca.documento["items"]:
            ws.cell(row=row, column=1, value=item["concepto"])
            ws.cell(row=row, column=2, value=item["base_legal"])
            ws.cell(row=row, column=3, value=item["pct"])
            row += 1


def _financiamiento_doc(ws: Worksheet, report: CostReport) -> None:
    fi = next((c for c in report.integracion_resuelta if c.code == "FI"), None)
    doc = (fi.documento or {}) if fi is not None else {}
    _title(ws, 1, "ANÁLISIS DEL COSTO DE FINANCIAMIENTO", size=14)
    _muted(ws, 2, 1,
           f"Tasa {doc.get('tasa_anual', 0):g} % anual — {doc.get('indicador', '')} · "
           f"{doc.get('fuente', '')} · publicada {doc.get('fecha_publicacion', '')}")
    _header(ws, 4, ["Periodo", "Egresos", "Ingresos", "Saldo", "Costo del periodo"])
    row = 5
    for periodo in doc.get("periodos", []):
        ws.cell(row=row, column=1, value=periodo["periodo"])
        for col, key in ((2, "egresos"), (3, "ingresos"), (4, "saldo"), (5, "costo")):
            ws.cell(row=row, column=col, value=periodo[key]).number_format = MONEY
        row += 1
    total = ws.cell(row=row, column=1, value="Costo de financiamiento")
    total.font = Font(bold=True, size=9)
    ws.cell(row=row, column=5, value=doc.get("total", 0.0)).number_format = MONEY
    if doc.get("total", 0.0) < 0:
        _muted(ws, row + 1, 1,
               "Negativo: el anticipo financia los trabajos antes de que el saldo "
               "cruce a favor del contratista. Es legal y se declara tal cual.")
```

`MONEY` above stands for exports.py's money number-format: grep `number_format` in the file first — if a shared constant exists, use it; if the format string appears inline (as in `_flujo`), define `MONEY = "<that exact string>"` once near the other module constants and use it in both new builders. Import `CATEGORIA_LABEL` from `klave_engine.costing.indirectos` and `Worksheet`/`Font` are already imported in exports.py.

In `_licitacion_workbook`, before `return workbook`:

```python
    _analisis_indirectos(workbook.create_sheet("Análisis de indirectos"), report)
    if any(c.code == "FI" and c.fuente == "analisis" for c in report.integracion_resuelta):
        _financiamiento_doc(workbook.create_sheet("Financiamiento"), report)
```

In `_caratula`, extend the `rows` list after `("Costo directo", ...)` — insert the five integration lines with their fuente:

```python
        *[
            (f"{line.description} ({line.percentage:g} %"
             + (", análisis" if line.fuente == "analisis" else ", declarado") + ")",
             line.amount)
            for line in report.integration.lines
        ],
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_exports.py tests/test_croquis.py tests/test_generadores.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/klave_engine/costing/exports.py tests/test_exports.py
git commit -m "feat(exports): analisis de indirectos y financiamiento como hojas de la licitacion, fuente por renglon en la caratula

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Web — desglose de campo y fuentes en parámetros

**Files:**
- Modify: `apps/web/lib/api.ts` (types + `CostingConfigResponse`)
- Create: `apps/web/components/DesgloseCampo.tsx`
- Modify: `apps/web/components/CostingConfigForm.tsx` (fuente hints)
- Modify: `apps/web/app/proyecto/[id]/parametros/page.tsx` (mount the editor)

**Interfaces:**
- Consumes: `GET /projects/{id}/costing-config` now returns `integracion: {code, pct, amount, fuente, faltantes}[]` (Task 7); config PUT already round-trips arbitrary `CostingConfigFull` fields.
- Produces:
  - api.ts: `export type RubroIndirecto = { concepto: string; categoria: string; importe: number; base: "mensual" | "unico" }`, `export type ComponenteIntegracion = { code: string; pct: number | null; amount: number | null; fuente: "analisis" | "declarado"; faltantes: string[] }`; `CostingConfigFull` gains `desglose_campo?: { rubros: RubroIndirecto[] } | null` and `cargos_adicionales?: { concepto: string; base_legal: string; pct: number }[]` and `financiamiento?: { tasa_anual: number; indicador: string; fuente: string; fecha_publicacion: string } | null`; `CostingConfigResponse` gains `integracion?: ComponenteIntegracion[]`.
  - `DesgloseCampo.tsx` exports `DesgloseCampoCard({ value, onChange }: { value: { rubros: RubroIndirecto[] } | null; onChange: (v: { rubros: RubroIndirecto[] }) => void })`.

**Before writing any code:** read `apps/web/node_modules/next/dist/docs/` for the app-router conventions this Next.js version uses, and read `PlantillaCampo.tsx` end-to-end — the new card must look and behave like its sibling (same Card/SectionTitle primitives, same ghost-row entry idiom, same save path through the page's config state).

- [ ] **Step 1: Extend `lib/api.ts`**

Add the three types above next to `CostingConfigFull` (~line 629) and the optional fields on `CostingConfigFull`/`CostingConfigResponse`. No new fetch helpers needed for the project page (config rides `getCostingConfig`/the existing save call the parametros page uses — read how the page saves before assuming names).

- [ ] **Step 2: Build `DesgloseCampoCard`**

`apps/web/components/DesgloseCampo.tsx` — a Card titled "Desglose de indirectos de campo" with:
- One table: Concepto (text input) / Categoría (select over the nine categories with Spanish labels — copy `CATEGORIA_LABEL` values from `indirectos.py` into a local `const CATEGORIAS`) / Importe (number, right-aligned tabular) / Base (mensual|único select) / a remove button.
- A ghost row at the bottom (empty inputs; typing a concepto materializes the row) — same idiom as the catalog matrix editor; read `GeneradorEditor.tsx` or the catalogo page's ghost-row implementation and follow it.
- A fixed, non-editable first line: "Personal técnico, administrativo y de servicio — se calcula de la plantilla de campo (abajo)" with muted styling, so nobody types the personal twice.
- A one-line note when any row has importe 0: "Renglones en $0 se muestran vacíos y no suman: captúralos o bórralos."

- [ ] **Step 3: Mount it on the parametros page**

In `parametros/page.tsx`, next to where `PlantillaCampo` renders (find it), add:

```tsx
<DesgloseCampoCard
  value={config.desglose_campo ?? null}
  onChange={(v) => setConfigField("desglose_campo", v)}
/>
```

using the page's existing config-update mechanism (it has `setField(group, key, value)` for grouped numbers; add a sibling `setConfigField(key, value)` for top-level fields if none exists — mirror how `plantilla_campo` edits are saved, since that is also a top-level config field edited outside `ConfigGroup`).

- [ ] **Step 4: Share override inputs**

Below the `DesgloseCampoCard` (same card or a small sibling card titled "Oficina central en esta obra"), two fields writing top-level config keys via the same save path: "Share de oficina central (%)" (number, maps to `oficina_share_pct`, empty = null = prorrateo derivado) and "Motivo del share" (text, maps to `oficina_share_motivo`, helper text: "Obligatorio, mínimo 15 caracteres — sin motivo escrito se usa el prorrateo derivado"). Add both keys to the api.ts `CostingConfigFull` optional fields (`oficina_share_pct?: number | null; oficina_share_motivo?: string`).

- [ ] **Step 5: Fuente hints on `CostingConfigForm`**

Give `ConfigGroup` an optional prop `fuentes?: Record<string, { fuente: string; pct: number | null }>` keyed by config key (`field_indirects_pct`, `office_indirects_pct`, `financing_pct`, `additional_charges_pct`). When a key has `fuente === "analisis"`, render the input disabled with the derived pct as its value and a small badge "análisis" (use the `Badge` primitive); when declared, render normally. The parametros page maps the `integracion` array from `CostingConfigResponse` (`CI-C → field_indirects_pct`, `CI-O → office_indirects_pct`, `FI → financing_pct`, `CA → additional_charges_pct`) and passes it only to the "Indirectos y sobrecosto" group.

- [ ] **Step 6: Verify**

Run: `cd apps/web && npx tsc --noEmit`
Expected: clean.

Then verify in the browser per the preview workflow: start the dev servers (`make api`, and the web preview via the launch config — never Bash for the web server), open `/proyecto/<id>/parametros` on a processed project, add a rubro row, save, confirm the row round-trips after reload, and screenshot the card. Fix and re-check until clean.

- [ ] **Step 7: Commit**

```bash
git add apps/web/lib/api.ts apps/web/components/DesgloseCampo.tsx apps/web/components/CostingConfigForm.tsx "apps/web/app/proyecto/[id]/parametros/page.tsx"
git commit -m "feat(web): desglose de campo editable en parametros y porcentajes con su fuente — el analisis apaga la casilla

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: Web — oficina central y tasa en el catálogo del taller

**Files:**
- Modify: `apps/web/lib/api.ts` (workspace fetchers)
- Create: `apps/web/components/IntegracionSection.tsx`
- Modify: `apps/web/app/catalogo/page.tsx` (mount next to `SalarioRealSection`, ~line 420)

**Interfaces:**
- Consumes: `GET/PUT /catalog/integracion` (Task 7).
- Produces:
  - api.ts: `export type IntegracionTaller = { oficina: { rubros: RubroIndirecto[]; volumen_anual_contratado: number }; financiamiento: { tasa_anual: number; indicador: string; fuente: string; fecha_publicacion: string } }`, `getIntegracionTaller(): Promise<IntegracionTaller>`, `putIntegracionTaller(body: IntegracionTaller, actor?: string)` — mirror the fetch-helper and actor-header idiom of the existing workspace calls (read `saveWorkspaceDefaults` at ~line 2379 and copy its shape).
  - `IntegracionSection.tsx` exports `IntegracionSection({ onChanged, onError, onNotice })` with the same props contract as `VigenciaSection` (read it first).

- [ ] **Step 1: Add the api.ts types + fetchers** (as specified above).

- [ ] **Step 2: Build `IntegracionSection`**

Two cards inside one section titled "Integración del precio":
1. **Oficina central** — same rubro-row editor as `DesgloseCampoCard` (extract the row-editor into a shared component in `DesgloseCampo.tsx` — export `RubrosEditor({ rubros, onChange, baseAnual }: { rubros: RubroIndirecto[]; onChange: (r: RubroIndirecto[]) => void; baseAnual?: boolean })` — rather than duplicating it; `baseAnual` hides the mensual/único select and labels the amount "Importe anual"), plus a "Volumen anual contratado (MXN)" number input and a muted line that renders the live derivation when both are set: `costo anual ÷ volumen = X.XXXX %`.
2. **Financiamiento** — four inputs: Tasa anual (%), Indicador (text, placeholder "TIIE 28 días"), Fuente (text, placeholder "Banxico SF43783"), Fecha de publicación (date). A muted line: "Sin los cuatro datos no hay análisis: el financiamiento se queda en porcentaje declarado."

Save button per section calling `putIntegracionTaller` with the merged object (a PUT always carries both halves — the endpoint stores them together), then `onChanged()`.

- [ ] **Step 3: Mount on the catalogo page**

In `apps/web/app/catalogo/page.tsx`, next to `<SalarioRealSection …/>` (~line 420):

```tsx
<IntegracionSection onChanged={reload} onError={setError} onNotice={setNotice} />
```

- [ ] **Step 4: Verify**

Run: `cd apps/web && npx tsc --noEmit` — clean.
Browser: open `/catalogo`, capture oficina rubros + volumen, confirm the derived pct line renders, save, reload, confirm round-trip. Then on a project: recompute from parámetros and confirm the "Indirectos de oficina" input in the config form now shows the análisis badge with the derived pct. Screenshot both.

- [ ] **Step 5: Full suite + commit**

Run: `pytest -q` (entire suite) — everything green.

```bash
git add apps/web/lib/api.ts apps/web/components/IntegracionSection.tsx apps/web/components/DesgloseCampo.tsx apps/web/app/catalogo/page.tsx
git commit -m "feat(web): oficina central y tasa de financiamiento del taller — el prorrateo se ensena mientras se captura

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Final acceptance (run after Task 11)

- [ ] `pytest -q` — full suite green.
- [ ] Demo project (declared mode): direct cost `157533681.21` and today's sale price unchanged.
- [ ] Analysis-mode walkthrough on a processed project: capture taller integracion + desglose campo + plantilla salaries → recompute → presupuesto shows fuente per component → `format=licitacion` exports without motivo → workbook carries "Análisis de indirectos" + "Financiamiento" sheets whose totals equal the Carátula's integration lines to the centavo.
- [ ] Declared-mode licitación export returns 409 with the per-component messages, and UT is not among them.
