# Primeros pasos — guía para el taller

Para el ingeniero de costos que abre Klave por primera vez. Quince minutos
del plano al presupuesto entregable.

## 0. Antes de subir nada

- Prueba la **obra de ejemplo** (botón en la pantalla vacía de Proyectos):
  una obra sintética que se procesa en segundos y muestra un presupuesto
  terminado — con su evidencia, sus supuestos y sus advertencias — para que
  veas qué entrega la herramienta antes de darle un plano tuyo.
- **Qué archivos abre**: DXF siempre. DWG se convierte con LibreDWG; si una
  hoja no abre, expórtala a DXF desde AutoCAD (`GUARDARCOMO` → DXF 2018) y
  súbela así. Una obra = un proyecto: sube todas sus hojas juntas.

## 1. Sube y deja leer

Arrastra las hojas a Proyectos. El motor convierte, detecta elementos
(castillos, trabes, muros, losas, zapatas, pilotes…), lee cuadros y notas,
separa las plantas por nivel y cuantifica. Una obra real de ~16 hojas toma
uno o dos minutos.

## 2. Verifica antes de confiar (Resumen → Ruta de verificación)

1. **Unidades** — si el plano no declara su unidad, nada lleva precio hasta
   que la confirmes. Es la decisión más importante de todas.
2. **Detecciones** — recorre Revisión (o el Visor): confirma lo correcto,
   excluye lo que no es un elemento. Tus verdictos sobreviven reprocesos.
3. **Supuestos** — alturas, secciones y porcentajes en Parámetros; cada
   línea del presupuesto dice qué supuso.

Hasta completar la ruta, pantallas y Excel salen sellados **SIN VERIFICAR**.

## 3. Haz tuyo el presupuesto

- **Tus claves**: en cada línea, "Concepto del taller" empareja tu catálogo
  (importado en Catálogo → Fuentes) con su clave, descripción y precio. Las
  sugerencias al 80 % o más aparecen solas; decides una vez y aplica a todos
  tus proyectos.
- **Tus precios**: Catálogo → Insumos (edítalos o importa CSV), vigencia con
  solicitud de cotización de vencidos, salario real y costo horario conforme
  al RLOPSRM.
- **Lo que el plano no trae**: "Agregar concepto" con motivo obligatorio, o
  reglas paramétricas por m² desde tus presupuestos anteriores (Catálogo →
  Plantillas).

## 4. Entrega

Presupuesto → Exportar: Excel Klave (con generadores y croquis), layouts
para OPUS y Neodata, catálogo de licitación con P.U. con letra y
descripciones LOPSRM, y la explosión de insumos. Programa y flujo salen del
mismo cálculo; ponle fecha de arranque y los días se vuelven calendario.

## 5. Calibra con tu gente (recomendado la primera semana)

Cuando tengas un presupuesto hecho a mano de la misma obra:

```bash
make eval-compare ENGINE=data/uploads/<proyecto> HUMAN=tu_presupuesto.xlsx
```

Compara concepto por concepto (por clave, por tu alias o por descripción),
señala unidades en desacuerdo y totales. Ahí se decide cuánto confiar y qué
corregir — y ese archivo es oro para nosotros.

## Dudas de vocabulario

El glosario vive en `/glosario` dentro de la app: detección, P.U., APU,
Fsr, explosión, vigencia, paramétrico, LOPSRM…
