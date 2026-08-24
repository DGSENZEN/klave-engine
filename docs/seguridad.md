# Seguridad, cuentas y roles

Qué puede hacer quién, cómo entran las cuentas, y qué protege al servidor.
Todo lo de esta página está implementado y probado; nada es aspiracional.

## Modos del servidor

| Modo | Cuándo | Comportamiento |
|---|---|---|
| **Abierto** | Sin base de usuarios (instalación local de un solo taller) | Sin cuentas; libertad local-first. El `X-Actor` del navegador firma la colaboración. |
| **Protegido** | Existe al menos una cuenta | Todo requiere sesión; la atribución es la del usuario firmado (el encabezado no se puede falsificar). |

`KLAVE_REGISTRATION=open` (default): cualquiera puede **fundar un taller
nuevo** (queda como su administrador, activo al instante) o **pedir unirse**
al taller existente (queda pendiente hasta que un administrador apruebe).
`KLAVE_REGISTRATION=invite_only`: solo los enlaces de invitación crean
cuentas — el registro y el alta por Google sin invitación se rechazan con
un mensaje claro, y la pantalla de entrada lo dice.

## Cuentas y sesiones

- **Contraseñas**: mínimo 10 caracteres, se rechazan las más comunes, las de
  caracteres repetidos y las que contienen el propio correo — con la razón
  en el mensaje. Aplica en registro, restablecimiento y cambio.
- **Sesiones**: token nuevo en cada login (HttpOnly, `Secure` en https,
  SameSite configurable); lista de sesiones con dispositivo/IP y "cerrar las
  demás" (con confirmación). Cambiar la contraseña o restablecerla revoca
  todas las demás sesiones.
- **Google**: `iss`/`aud`/`exp` validados y `email_verified` exigido. Una
  cuenta existente **nunca** se liga por coincidencia de correo: se liga
  desde *Tu cuenta* con la sesión abierta.
- **Recuperación**: enlaces de un solo uso con expiración; sin proveedor de
  correo, el enlace se muestra al administrador (y el outbox local es solo
  texto, permisos 600, barrido a los 7 días).
- **Anti-abuso**: rate limits por usuario (o IP sin sesión) en login,
  registro, recuperación, subida, procesamiento, lectura con IA, matches y
  exports; CSRF por origen en toda mutación; en producción solo los
  orígenes configurados y arranque que valida la configuración.

## Roles (RBAC)

Dos roles de taller y tres de proyecto. La regla de diseño: **el trabajo
diario del ingeniero de costos nunca requiere administrador; lo
estructural y lo destructivo, siempre.**

| Acción | Miembro activo | Administrador |
|---|---|---|
| Ver y trabajar los proyectos a los que tiene acceso (viewer/editor/owner por proyecto) | ✓ según rol de proyecto | ✓ todos los del taller |
| Subir proyectos, procesar, revisar, ajustar cantidades (con motivo), exportar | ✓ | ✓ |
| Editar precios de insumos, adoptar referencias, claves del taller (aliases), mapeos de levantamiento, factores paramétricos, rendimientos | ✓ | ✓ |
| **Importar** precios, matrices, fuentes, catálogo propio, plantillas | — | ✓ |
| **Borrar** plantillas y reglas paramétricas | — | ✓ |
| Reprecios masivos: actualizar vencidos por índice, aplicar salario real, costo horario, guardar índices | — | ✓ |
| Valores del taller (defaults), renombrar taller, invitar, aprobar, roles, recuperación | — | ✓ |
| Borrar un proyecto **con archivos** (`purge`) | dueño del proyecto o admin | ✓ |

Cada taller tiene su propio catálogo (`catalogs/<workspace>.db`), sus
defaults y sus eventos: nada cruza entre talleres, ni siquiera por error de
código de rol (el aislamiento es por archivo y por consulta, no por if).

## Auditoría y trazabilidad

Invitaciones, aprobaciones, roles, recuperaciones, cambios de contraseña y
de taller quedan en la bitácora (`/equipo`, registro de actividad) con
actor y fecha. Cada petición lleva un id (`rid=` en logs, `X-Request-Id` en
la respuesta) y los correos se redactan en los logs (`a***@taller.mx`).
