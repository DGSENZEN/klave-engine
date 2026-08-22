# Lectura asistida por IA

Las reglas leen geometría. Hay cosas que solo se leen *viendo* la hoja: el
cuadro de castillos dibujado, las notas de materiales, el nivel en el cajetín,
una marca al lado de su sección. Para eso el motor **renderiza cada marco de
hoja a una imagen** (`renders/<código>.png`, también visible en el visor como
«img») y, si el servidor tiene `ANTHROPIC_API_KEY`, un modelo de visión
(`claude-opus-5`) lee la imagen y devuelve una lectura estructurada:

- cajetín: clave, título, nivel, escala;
- notas: f'c por familia, fy, recubrimientos, desplante, sistema de losa;
- elementos: marca, familia, sección, armado, estribos, longitud (pilotes), con
  una confianza por elemento y el texto de donde lo leyó;
- dudas: lo ilegible.

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
