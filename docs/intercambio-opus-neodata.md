# Intercambio con OPUS y Neodata

Los formatos nativos de OPUS y Neodata son propietarios y cerrados; Klave no
los lee ni los escribe. Lo que sí comparten ambos con cualquier taller es el
**Excel**: sus asistentes de importación lo aceptan y sus reportes lo
exportan. Klave trabaja con esa capa.

## Hacia OPUS / Neodata (exportar)

`Presupuesto → Exportar`:

| Opción | Qué produce |
|---|---|
| Excel para OPUS | una hoja plana Clave / Descripción / Unidad / Cantidad / Precio Unitario / Importe, sin celdas combinadas, para el asistente de importación de presupuesto |
| Excel para Neodata | la misma hoja con los encabezados que Neodata espera (Código / Concepto / Unidad / Cantidad / P.U. / Monto) |
| Catálogo de licitación | el catálogo de conceptos con partidas, P.U. con número y con letra, importes, subtotal, IVA y total con letra (LOPSRM); el P.U. es el precio de venta (costo directo × factor de sobrecosto) |
| Licitación con descripciones LOPSRM | el mismo catálogo con la descripción larga generada de cada concepto («Suministro y colocación de …, incluye: …, P.U.O.T.»), derivada de su matriz |
| Explosión de insumos | cada insumo que consume el presupuesto (APU × cantidad) con su importe y su reparto por partida; también es una hoja del Excel completo |
| Excel completo (Klave) | carátula, presupuesto, APUs, generadores con croquis, programa y flujo |

## Desde OPUS / Neodata (importar)

### Precios de insumos

`Catálogo → Importar precios` acepta CSV/XLSX con una columna de clave y una de
precio (los encabezados de ambos programas se reconocen). Las filas importadas
quedan etiquetadas **cotización** con el nombre del archivo como fuente.

### Conceptos con sus matrices

`Catálogo → Importar matrices (OPUS/Neodata)` lee el reporte "catálogo de
conceptos con insumos" que exportan ambos programas: una fila por concepto
seguida de las filas de su matriz. Se reconocen dos disposiciones:

1. **Sin columna Tipo** (la exportación usual): la fila de concepto no trae
   cantidad; las filas de insumo traen la cantidad por unidad de concepto y su
   costo unitario.
2. **Con columna Tipo** (`CONCEPTO` / `INSUMO`), que es la disposición
   explícita que Klave documenta para cualquier hoja hecha a mano.

Encabezados reconocidos (con o sin acentos):

| Campo | Encabezados |
|---|---|
| clave | Clave, Código, Code, Id |
| descripción | Descripción, Concepto, Nombre |
| unidad | Unidad, U, UM |
| cantidad | Cantidad, Cant., Cantidad por unidad |
| costo | Costo, Costo unitario, Precio, Precio unitario, P.U. |
| rendimiento (opcional) | Rendimiento, Rend., Unidades/día |
| partida (opcional) | Partida, Fase, Capítulo, Grupo |

Reglas honestas:

- Un insumo con costo cero o vacío es "por cotización": no se importa y la
  matriz de su concepto queda sin él; el resultado lo dice fila por fila.
- Un concepto sin insumos con cantidad no se importa: sin matriz no hay precio.
- Un insumo en `%` (herramienta menor como porcentaje de mano de obra) se
  liga al recurso `EQ-HERRAMIENTA` con esa fracción.
- El tipo de recurso se deduce del prefijo de la clave (MO-, MAT-, EQ-) o de
  las palabras de la descripción (cuadrilla, oficial, equipo…); revisa los
  que queden como material por omisión.
- Los conceptos importados son **manuales** (sin regla de lectura del plano):
  toman cantidad por ajustes documentados o al ligarlos a un símbolo/capa del
  levantamiento. Un concepto ya existente conserva su regla y recibe la
  descripción, unidad y matriz importadas.
- Los precios importados se etiquetan **cotización** con la fuente indicada;
  nunca se presentan como precios de mercado.
