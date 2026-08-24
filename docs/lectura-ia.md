# Lectura asistida por IA

Las reglas leen geometría. Hay cosas que solo se leen *viendo* la hoja: el
cuadro de castillos dibujado, las notas de materiales, el nivel en el cajetín,
una marca al lado de su sección. Para eso el motor **renderiza cada marco de
hoja a una imagen** (`renders/<código>.png`, también visible en el visor como
«img») y, si el servidor tiene credenciales de IA, un modelo de visión lee
la imagen y devuelve una lectura estructurada.

Dos proveedores con el mismo contrato, elegidos con `KLAVE_AI_PROVIDER`:

- **Claude** (`ANTHROPIC_API_KEY`): modelo por defecto `claude-opus-5`.
- **Gemini** (`GEMINI_API_KEY` o `GOOGLE_API_KEY`): por defecto
  `gemini-2.5-pro`.
- `auto` (por defecto) usa el que tenga credenciales, Claude primero. Una
  elección explícita sin credenciales se reporta como *no configurada* —
  nunca cae en silencio al otro proveedor. `KLAVE_AI_MODEL` sobreescribe el
  modelo. La lectura devuelve:

- cajetín: clave, título, nivel, escala;
- notas: f'c por familia, fy, recubrimientos, desplante, sistema de losa;
- elementos: marca, familia, sección, armado, estribos, longitud (pilotes), con
  una confianza por elemento y el texto de donde lo leyó;
- dudas: lo ilegible.

## Cobertura: el motor descubriendo lo que se le fue

En cada hoja de planta, el modelo además **cuenta** cuántas instancias de
cada familia discreta están dibujadas (castillos, columnas, trabes, zapatas,
pilotes, escaleras…). Ese conteo se compara con lo que los detectores de
reglas encontraron en el mismo marco, y una discrepancia **no cambia ninguna
cantidad**: marca la hoja — «en E-02 la IA cuenta 6 castillos; el motor
detectó 4 — revisa esa hoja». Los faltantes silenciosos se vuelven tareas de
revisión visibles en *Lectura*. Las familias continuas (muros, losas) no se
comparan: no tienen un conteo natural de instancias.

Cuando la revisión confirma que algo falta, se registra en **Revisión →
Elementos omitidos por el motor**: entra al presupuesto como *levantamiento
manual* con el nombre del ingeniero y su nota (familia, marca, cantidad,
longitud o área en metros, sección si está declarada). El generador lo dice
tal cual — «Incluye N elemento(s) del levantamiento manual del ingeniero» —
y la nota le sirve al equipo de Klave como reporte de la falla de detección.

## Qué hace con lo leído — y qué no

- Todo queda en `ai_reads.json` con procedencia (hoja, modelo, tokens) y se
  muestra en *Lectura → Lectura asistida por IA* para que el ingeniero lo vea.
- Al **reprocesar**, las lecturas entran al inventario de especificaciones
  como fuente `ia`, la de **menor rango**: un cuadro, un detalle o una nota
  leídos por reglas mandan; la IA solo completa la sección o el armado de una
  marca que las reglas no leyeron (y lo dice en la evidencia: «lectura IA de
  la imagen de la hoja (por confirmar)»). Los f'c leídos solo se toman cuando
  las notas no los declararon.
- **Nunca** cuantifica ni pone precio por sí sola.

## Operación

- `POST /projects/{id}/ai-read` arranca la lectura en segundo plano (una
  petición por hoja; ~22 hojas en Marina). `GET /projects/{id}/ai-reads`
  devuelve estado y lecturas; `GET /projects/{id}/renders/{código}.png` la
  imagen de la hoja.
- Sin credenciales el botón queda deshabilitado y la API responde 409
  `ai_not_configured`; nada finge haber leído.
