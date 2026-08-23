# Precios que no se pudren: vigencia, cotización e índices

Un catálogo de precios envejece a la velocidad del cemento. Klave no inventa
precios de mercado; lo que sí hace es decir cuántos meses tiene cada precio,
cuáles usa este presupuesto, pedir cotización por ti e importar la respuesta,
y traer un precio viejo a hoy por un índice que el taller mantiene.

## Edad de cada precio

Cada insumo tiene `vigencia` (AAAA-MM). Estados:

| Estado | Edad |
|---|---|
| vigente | ≤ 6 meses |
| revisar | 7–12 meses |
| vencido | > 12 meses o sin vigencia |

`GET /catalog/vigencia` lista todos con su edad; el catálogo muestra el chip
junto a cada fuente. El presupuesto advierte cuáles insumos **que usa** están
vencidos ("N insumos con precio de más de 12 meses: MAT-CEM, MO-PEON…") y
anota los que conviene revisar.

## Solicitud de cotización

`Catálogo → Solicitar cotización` (`GET /catalog/cotizacion.xlsx?status=vencido|revisar|all`
o `?codes=MAT-CEM,MAT-ARENA`) genera el XLSX con clave, descripción, unidad,
precio actual y vigencia, más las columnas vacías **Precio cotizado**,
Proveedor, Vigencia y Observaciones. El proveedor lo llena y el mismo archivo
se importa con *Importar precios*: cada renglón con precio entra como
**cotización** con el nombre del archivo como fuente.

## Actualizar por índice

`Catálogo → Índices` guarda la tabla del taller `{AAAA-MM: valor}` con su
fuente (por ejemplo el INPP de la construcción de INEGI; Klave no trae valores
precargados porque no inventa cifras oficiales). `POST /catalog/indices/roll-forward`
con `status` o `codes` aplica a cada insumo el factor `índice(hoy) / índice(vigencia)`;
si un mes no está publicado se usa el mes anterior más cercano, nunca uno
posterior. El insumo queda con tipo **calculado**, vigencia de hoy y la
fuente "precio anterior × índice X 2025-06→2026-08 (factor 1.0600)". Un
precio actualizado por índice sigue siendo una estimación: la cotización
manda.
