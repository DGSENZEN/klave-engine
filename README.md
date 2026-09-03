# Klave

Ingeniería de costos automatizada a partir del plano: se sube el DWG/DXF de
una obra, el motor lee sus disciplinas con detectores deterministas (solo
CPU, sin GPU) y el taller trabaja el resultado hasta el cierre del
contrato — presupuesto, programa, flujo, estimaciones — en una app web
colaborativa en tiempo real.

La doctrina que gobierna todo: **nada se inventa**. Cada cantidad carga su
evidencia y sus supuestos; lo que no tiene unidad confiable no se enseña
como dinero (una sola autoridad decide el veredicto); el concepto sin
precio queda visible como hueco, nunca en $0; y las convenciones mexicanas
(EJES/TRABES/CASTILLO/ZAPATA, RLOPSRM, OPUS/Neodata) son de primera clase.

## Qué hace hoy

El proyecto se trabaja como un **tablero de nodos** — un lienzo con seis
nodos conectados en el orden del proceso, cada uno con sus hechos y su
candado de administrador:

- **Planos** — subida con pre-escaneo («qué datos jala» cada hoja, según el
  registro real de disciplinas), conversión DWG→DXF, lectura con cobertura
  declarada por archivo (ok/parcial/ilegible), índice de prefabricados, y
  el visor: medidas al pasar el cursor, revisión con teclado (C confirmar,
  X excluir, ← → recorrer), medición y conteos humanos, y la ida y vuelta
  con el dinero (concepto, catálogo y ajuste sin salir del plano).
- **Disciplinas** — estructural a profundidad (ejes por marco, columnas y
  castillos anclados, zapatas, trabes, tableros de losa, muros, cadenas
  con sección del cuadro); hidrosanitaria (tubería por diámetro, bajadas
  entre niveles), cancelería (piezas por clave), acabados (claves ancladas
  a su local), albañilería (tabique en m² con vano descontado) y el fondo
  arquitectónico como sustrato que se ve pero jamás cobra. Lo demás se lee
  como levantamiento honesto.
- **Revisión** — la ruta de verificación (unidades, detecciones,
  supuestos) con firma y autor; riesgos agrupados (una tarjeta por tipo
  con su cuenta y sus miembros, la causa antes que el síntoma); el
  Diagnóstico con hallazgos accionables y el copiloto que los resuelve con
  acciones previsualizadas.
- **Catálogo del taller** — insumos y matrices de precio unitario al
  estilo OPUS (hoja jerárquica, celdas que guardan al salir, recurso por
  teclado), ficha técnica extraída del texto de cada concepto (f'c, fy,
  t.m.a., acabado…) que también decide en el matcher de referencias,
  fuentes oficiales (CDMX, SICT) con vigencia, salario real (Fsr) y costo
  horario por RLOPSRM, e importación de OPUS/Neodata y destajos con
  deshacer.
- **Presupuesto** — partidas plegables con su peso, precios con fuente,
  ajustes documentados con autor, versiones comparables, y la
  **integración como análisis**: desglose de indirectos renglón por
  renglón, financiamiento calculado del flujo a una tasa capturada, en
  modo dual (el porcentaje declarado es el respaldo; el importe gana
  cuando el análisis existe). Exporta XLSX (formato Klave o licitación,
  OPUS, Neodata), CSV y generadores.
- **Programa y contrato** — programa de obra con precedencias reales (el
  colado espera a su cimbra), flujo con anticipo y retenciones,
  estimaciones con generadores, convenios, bitácora, ajuste de costos y
  finiquito.

Todo colabora en vivo (presencia, actividad y cambios por SSE) y funciona
**local-first sin cuentas**; al crear la primera cuenta el taller pasa a
modo protegido con roles por proyecto (viewer/editor/owner) y candados que
solo abre el administrador o el owner.

## Cómo usarlo

Requiere Python 3.11+, [uv](https://docs.astral.sh/uv/) y Node 20+.

```bash
make install          # dependencias de Python (uv sync)
make web-install      # dependencias de la web
cp .env.example .env  # opcional: convertidor, límites, cuentas
```

Arranca los dos procesos y abre la app:

```bash
make api              # FastAPI en :8000
make web              # Next.js en :3000  → abre http://localhost:3000
```

Desde ahí el flujo es el de la pantalla: **sube tu plano** (el diálogo dice
qué datos jala cada hoja) → se procesa → el proyecto abre en su tablero →
recorre Planos y Revisión (verifica unidades, detecciones y supuestos: sin
esa firma el dinero se muestra bloqueado o marcado) → dale precio a los
huecos desde el Catálogo → trabaja Presupuesto, Programa y Contrato.

### Conversión DWG

El motor nunca lee DWG directo: usa un convertidor externo. Con LibreDWG
(`brew install libredwg` en macOS):

```bash
# .env
KLAVE_CONVERTER_EXECUTABLE_PATH=/opt/homebrew/bin/dwg2dxf
```

Los proyectos que ya traen DXF funcionan sin convertidor. La conversión
corre una escalera de reintentos y un saneador de DXF malformados; las
referencias externas (xref) se incorporan cuando el archivo está junto.

### Cuentas (opcional)

Sin configurar nada, la app corre en modo abierto: sin sesiones, todos
pueden todo — local-first. Para el modo protegido:

```bash
make users-db-up      # Postgres dedicado para cuentas (puerto 5433)
```

La primera cuenta registrada es el administrador y activa el modo
protegido. Google OAuth es opcional (`KLAVE_AUTH_GOOGLE_ID/SECRET`). La
base de cuentas es deliberadamente independiente de los datos de obra.

### Proyecto de demostración y CLI

```bash
make demo-data        # genera el proyecto DXF sintético
make process-demo     # corre el pipeline completo
```

O etapa por etapa: `uv run klave ingest|convert|parse|process|report <ruta>`.
Cada etapa escribe artefactos JSON inspeccionables bajo
`<proyecto>/processed/runs/<run>/` y reportes legibles.

La API se explora en `http://localhost:8000/docs`; las rutas leen
artefactos ya generados, no recomputan por petición.

## Evals: el cerco del motor

```bash
make eval-gold        # el gold set: fixtures reales congelados (~13 s)
make eval-demo        # la suite de regresión sobre el demo
```

El gold set fencea cantidades por concepto sobre planos reales. Cambiar una
cantidad a propósito exige recapturar el fixture y **declararlo en el
commit** — un gold rojo sin declaración es una regresión, no un detalle.
Ver [docs/evals.md](docs/evals.md).

## Estructura del repositorio

```text
apps/api                  FastAPI (rutas delgadas, sin lógica de negocio)
apps/web                  Next.js — el tablero, el visor y todas las pantallas
packages/klave_engine
  conversion/ ingestion/  DWG→DXF y manifiesto del proyecto
  dxf/ geometry/ graph/   parseo ezdxf, primitivas, índice espacial, grafo
  detection/              detectores deterministas + disciplines/ (registro
                          por disciplina: ruteo, voto de contenido, suites)
  takeoff/ costing/       cuantificación; catálogo, APU, presupuesto,
                          integración (indirectos/financiamiento), programa,
                          flujo, exports, hallazgos, presentación del dinero
  risks/                  reglas de riesgo + agrupado (una tarjeta por tipo)
  evals/                  gold set, regresión, recall
tests/                    pytest (unitarias, fixtures, contratos de API)
docs/                     primeros-pasos, despliegue, principios de interfaz,
                          auditorías, specs y planes (superpowers/)
```

## Desarrollo

```bash
make test         # pytest
make lint         # ruff
make typecheck    # mypy
npm --prefix apps/web run lint
npx --prefix apps/web tsc --noEmit
```

Guías: [docs/primeros-pasos.md](docs/primeros-pasos.md) (la guía del
taller), [docs/principios-de-interfaz.md](docs/principios-de-interfaz.md)
(las reglas escritas de la interfaz),
[docs/despliegue.md](docs/despliegue.md) y `make prod-up` para producción
con Docker.

Esto **no** es un sistema de aprobación estructural y los precios de
referencia son datos editables, no cotizaciones de mercado. El resultado se
inspecciona y se corrige por un ingeniero de costos — la app está hecha
exactamente para ese circuito.
