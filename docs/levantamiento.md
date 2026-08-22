# Levantamiento por hoja — instalaciones, acabados, cancelería y demás

Un plano estructural se lee como elementos (zapatas, trabes, tableros de
losa) que el motor cuantifica por regla. Las demás disciplinas no se dibujan
así: son **símbolos** (bloques — una salida sanitaria, una luminaria, una
cámara), **trazos** sobre una capa (tubería hidráulica, ducto, línea de gas),
**etiquetas** repetidas (V-1, P-3, CA-15 en cancelería, carpintería, plafones)
y **áreas** (contornos cerrados o achurados de pisos y plafones).

La lectura honesta de esas hojas es un inventario — el *levantamiento* — y
un conteo **no es una cantidad hasta que el taller lo asigna a un concepto**.

## Qué se lee

Para cada hoja (`inventory.json`, sección *Levantamiento por hoja* en
Lectura, hoja *Levantamiento* del XLSX):

| Tipo | Qué cuenta | Unidad |
|---|---|---|
| Símbolo | inserciones de bloque por nombre y capa | PZA |
| Etiqueta | marcas cortas repetidas en textos y en atributos de burbujas de nomenclatura | PZA |
| Trazo | longitud de líneas/polilíneas/arcos por capa (≥ 1 m) | M |
| Área | contornos cerrados y achurados por capa (≥ 0.25 m²) | M2 |

Se omiten las capas de anotación (cotas, textos, cajetín, ejes) y los
símbolos del aparato de la hoja (pie de plano, norte, N.P.T., bloques
anónimos). Cuando la hoja tiene marcos (plantas), cada conteo se parte por
planta. Las especificaciones leídas (Ø, PEAD 19MM, CAL. 22) se listan junto a
la hoja. La disciplina se infiere del nombre del archivo o, si no dice nada,
de sus capas y bloques.

Las hojas de instalaciones, cancelería y carpintería **no pasan por los
detectores estructurales**: sus círculos y cajas son salidas y equipos, no
zapatas. Una hoja con nombre desconocido se lee como estructura.

## Cómo se convierte en presupuesto

En *Lectura*, cada renglón del levantamiento ofrece `concepto (PZA|M|M2)…`.
Asignar un símbolo, etiqueta, capa o área a un concepto crea una **regla del
taller** (`inventory_mappings`, vale para todos los proyectos) y recalcula el
presupuesto: el concepto recibe la cantidad (conteo × factor) con la nota
`Levantamiento: 16 símbolos «DESCSAN1» en 05 SANITARIO…` y su partición por
planta. Un concepto sin matriz ni precio adoptado no recibe línea — se avisa.

Flujo típico del taller con su catálogo propio:

1. *Catálogo → Catálogo propio*: sube el XLSX/CSV del taller (clave,
   descripción, unidad, precio unitario).
2. *Catálogo → Conceptos*: crea el concepto (p. ej. `INS-001 Salida sanitaria`)
   y, desde la búsqueda de referencias, aplica el renglón del catálogo propio
   como su **P.U.** (la matriz queda en pausa; la procedencia viaja al
   presupuesto y al XLSX).
3. *Lectura → Levantamiento*: asigna `DESCSAN1 → INS-001`. El presupuesto se
   recalcula: 16 SAL × P.U.

## Límites

- Conversión: `dwg2dxf` (LibreDWG) no lee todo — un archivo puede llegar
  vacío o sin su xref arquitectónico; la hoja lo dice en Lectura.
- Una burbuja de nomenclatura cuenta como elemento aunque su etiqueta
  aparezca una sola vez; un texto suelto repetido una vez se toma como título
  de detalle y no se cuenta.
- Las áreas solo existen cuando el dibujo las cierra; los acabados marcados
  con símbolos (QRF, CAMBIO-ACABADO) se cuentan como símbolos.
