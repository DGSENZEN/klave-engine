# Evaluación del motor

Dos niveles, ambos en `make`:

- `make eval-demo` — la suite sintética (`evals/regression_suite.py`): un plano
  generado con verdad conocida. Debe dar PASS siempre.
- `make eval-gold` — el **gold set** de planos reales (`evals/gold/*.json`).
  Los planos no se versionan; cada entrada guarda el hash de sus archivos y
  se salta con aviso si no están en esta máquina.

## Cómo crece el gold set

Cada entrada nace de un proyecto procesado y **absorbe las revisiones
humanas** del visor: una detección marcada con X sale de las etiquetas
esperadas, una marcada con C queda fijada. El estado dice cuánto confiar:

| estado | significado |
|---|---|
| `baseline` | sin revisiones: protege contra regresiones, no es verdad |
| `partial` | hay revisiones; las excluidas son deuda visible del detector |
| `verified` | el ingeniero firmó el paso de detecciones; se exige F1 = 1 |

```bash
make gold-capture ROOT=data/uploads/<proyecto> ID=<clave-del-plano>
make eval-gold
```

`--fresh` (que `make gold-capture` ya usa) etiqueta con una corrida del motor
actual, para que la base nunca quede atrás del parser. Recaptura una entrada
después de revisar detecciones en el visor; el runner falla si una confirmada
desaparece, si una entrada `verified` deja de ser perfecta, o si cualquier tipo
cae por debajo de su F1 base.


## Dinero en el gold set

Detectar bien no basta: un cambio en una regla, una matriz o un precio
semilla debe verse como cantidad y como pesos. Cada entrada del gold puede
llevar `money`:

```json
"money": {
  "concepts": {"EST-004": {"quantity": 449.277, "unit": "M2", "tolerance_pct": 10, "source": "engine"}},
  "direct_cost": 777450.5,
  "direct_cost_tolerance_pct": 5,
  "unpriced": []
}
```

- `make eval-gold` (`gold run`) vuelve a correr el motor puro sobre el
  plano — catálogo por defecto, precios de referencia, supuestos por
  defecto, sin revisiones ni catálogo del taller — y compara concepto por
  concepto (desviación contra `tolerance_pct`), el costo directo contra su
  tolerancia, y falla si aparece un concepto que el gold no conocía.
- `uv run python -m klave_engine.evals.gold money [--only id]` captura la
  cerca actual del motor (`source: engine`) en las entradas existentes sin
  tocar etiquetas ni revisiones.
- Donde haya verdad, edita a mano: `"source": "human"` con la cantidad del
  levantamiento y su tolerancia; `money` conserva esas filas al recapturar.

La cerca del motor no es verdad: es lo que el motor decía cuando se capturó,
para que ningún cambio mueva dinero sin que alguien lo vea y lo acepte
(recaptura a propósito, con el commit que explica por qué).

## Comparar contra un presupuesto humano

La calibración que una firma hace en sus primeros proyectos: el presupuesto
del motor contra el que hizo su gente, concepto por concepto.

```bash
make eval-compare ENGINE=data/uploads/<proyecto> HUMAN=presupuesto_humano.xlsx
```

`ENGINE` es la raíz del proyecto (usa la corrida activa y el recálculo con
revisiones si existe) o un `cost_report.json`. `HUMAN` es cualquier XLSX/CSV
con columnas de clave, descripción, unidad y cantidad (una exportación de
OPUS/Neodata o el generador del taller); el precio es opcional. Los conceptos
se emparejan en tres pasadas, cada una etiquetada en la columna
"Emparejado por":

1. **clave** — la del humano contra la del motor **o la clave del taller**
   que la línea ya imprime (los aliases trabajan aquí);
2. **descripción** — para lo que quedó, el mismo matcher del catálogo
   (unidad obligatoria, ≥ 60 % con el porcentaje visible);
3. lo demás queda como "solo humano" / "solo motor" — nada se oculta.

Las unidades se normalizan (`m²` = `M2`); si aun así difieren, la fila dice
"unidad distinta" y **no** se compara la cantidad. La salida es una tabla
Markdown con Δ % por concepto ordenada de la peor diferencia a la mejor y un
resumen: mediana de |Δ|, cuántos dentro de ±10 %, el peor, y — si el archivo
trae importes — el total del motor contra el del humano.
