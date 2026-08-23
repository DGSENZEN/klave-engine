# Plantillas y paramétricos: lo que el plano no dice, propuesto desde tu historia

Un presupuesto de vivienda tiene 150–300 conceptos; el plano estructural da
unos 40. El resto (instalaciones, herrería, limpieza, acarreos, fletes…) el
taller lo arma de memoria, copiando el último proyecto parecido. Klave hace
esa copia por ti, la escala al proyecto nuevo y la marca como propuesta.

## Plantilla

`Catálogo → Plantillas → Importar presupuesto anterior`: sube el presupuesto
de un proyecto terminado (XLSX/CSV con clave, unidad, cantidad y de
preferencia descripción y precio) y captura sus **m² construidos** y su
tipología (casa habitación, nave, edificio…).

Por cada renglón:

1. Se busca el concepto de Klave: por **alias** (la clave ya ligada), por la
   propia clave si ya existe, o por **coincidencia** de descripción (≥ 75 %).
2. Si no hay concepto equivalente y el renglón trae precio, se crea un
   **concepto manual** con esa clave, descripción y unidad, con el precio
   del presupuesto adoptado (fuente: la plantilla).
3. Se guarda una **regla paramétrica**: `cantidad ÷ m²` por m² construido.
   Si el concepto lo lee el motor (muros, losas, castillos…), la regla queda
   marcada *solo para comparar*: nunca propone una línea que el plano ya dio.

Los renglones sin precio y sin concepto equivalente no se crean; el resultado
los lista.

## Paramétricos en un proyecto nuevo

Al calcular, para cada regla activa:

- **base**: m² construidos (suma de los tableros de losa de superestructura
  leídos del plano, o el valor capturado en Parámetros → Área construida),
  plantas de superestructura, un lote por proyecto, o locales de un tipo
  (`local:baño`, `local:interior`…) leídos de la arquitectura;
- **cantidad propuesta** = factor × base;
- la línea entra al presupuesto con la etiqueta **paramétrico**, confianza
  50 % y una nota que dice factor, base, cómo se leyó la base y la fuente
  ("Lote 02 (320 m²)"). Si el concepto ya tiene cantidad leída del plano o del
  levantamiento, la regla no la toca.

Las líneas paramétricas se editan como cualquier otra (fijar cantidad con
motivo) y se versionan igual. Las reglas se editan (factor, nota, activar/
desactivar) en Catálogo → Plantillas; una regla escrita a mano
(`POST /catalog/parametrics`) sirve igual que una importada.

## Límites honestos

- El factor por m² es la regla más simple posible; dos casas del mismo tamaño
  con programas distintos dan cantidades distintas. Por eso la línea es una
  **propuesta marcada**, nunca una lectura, y el presupuesto la anuncia.
- Sin tableros de losa leídos y sin área capturada, las reglas por m² no
  proponen nada y lo dicen en las advertencias.
- Los paramétricos por local necesitan una planta de arquitectura con locales
  nombrados (ver `docs/acabados.md`).

## Indicadores de sanidad y completitud

Al calcular, el presupuesto trae `indicators` (`costing/indicadores.py`):

| Indicador | Rango típico (casa habitación) |
|---|---|
| kg de acero por m³ de concreto | 80–160 kg/m³ |
| m² de cimbra por m³ de concreto | 4–12 m²/m³ |
| m³ de concreto por m² construido | 0.25–0.55 m³/m² |
| costo directo por m² construido | $7 000–22 000 $/m² |

Fuera de rango es una **señal** (aparece en Advertencias y en la tarjeta
"Indicadores de sanidad"), nunca una corrección. Además, la participación de
cada partida en el costo directo se compara contra la plantilla del taller
(la primera con participaciones guardadas): una partida que la plantilla
tiene con ≥ 2 % y este presupuesto no, se lista como **faltante** —
"Partidas que tu plantilla tiene y este presupuesto no: INSTALACIONES (11 %)".
Ese es el error más caro de un presupuesto (la omisión), atrapado antes de
entregar.
