# Producción: web en Vercel, motor en servidor persistente

El proyecto Vercel `klave-web` pertenece al equipo `dgsenzens-projects`.
Su Root Directory es `apps/web`, framework Next.js y Node.js 24.x.
La configuración aplicable es `apps/web/vercel.json`. El `vercel.json`
de la raíz corresponde al experimento de dos servicios, no a este despliegue.

## Conectar la API

En Settings → Environment Variables del proyecto Vercel:

| Variable | Valor de producción |
|---|---|
| `KLAVE_LOAD_DOTENV` | `0` (ya configurado) |
| `NEXT_PUBLIC_API_URL` | Origen HTTPS real de FastAPI, sin `/api` ni slash final |

El navegador llama directamente a FastAPI: `/projects`, `/auth`, `/events`,
etc. Las subidas y SSE no pasan por una función de Vercel. Este modo no usa
el binding `KLAVE_APP_URL` ni el proxy `/api` de Next.js. Cambiar una variable
`NEXT_PUBLIC_*` exige un nuevo build.

En el servidor del motor, usando los valores reales:

| Variable | Valor |
|---|---|
| `KLAVE_ENV` | `production` |
| `KLAVE_LOAD_DOTENV` | `0` si el servicio inyecta las variables |
| `KLAVE_WEB_ORIGIN` | Origen HTTPS exacto del frontend publicado |
| `KLAVE_API_PUBLIC_PREFIX` | Cadena vacía (API pública sin prefijo) |
| `KLAVE_REGISTRATION` | `invite_only` |
| `KLAVE_COOKIE_SECURE` | `true` |
| `KLAVE_COOKIE_SAMESITE` | `lax` con `app.example.com` y `api.example.com` |
| `KLAVE_USERS_DATABASE_URL` | PostgreSQL de producción, configurado en el servidor |
| `KLAVE_DATA_DIR` | Directorio persistente de proyectos, catálogos y resultados |
| `KLAVE_REPORTS_DIR` | Directorio persistente de reportes |

Deja `KLAVE_COOKIE_DOMAIN` sin definir: la sesión puede ser una cookie del
host de la API. Si web y API usan sitios distintos (por ejemplo,
`klave-web.vercel.app` y un dominio propio para la API), hace falta
`KLAVE_COOKIE_SAMESITE=none`; el navegador todavía puede bloquear cookies
de terceros. Para producción, usa subdominios del mismo dominio y `lax`.
Configura el origen exacto de la web; no habilites comodines de Vercel.

El servidor debe ejecutar un único proceso API con disco persistente,
PostgreSQL, backups y el conversor DWG del Dockerfile. Para EC2, usa
[la guía del backend](ec2.md) y `docker-compose.ec2.yml`: no inicia otra web
y solo publica HTTPS/HTTP mediante Caddy. `docker-compose.prod.yml` sigue
siendo la alternativa que aloja también el frontend en el servidor.

## Publicar y verificar

1. Confirmar el dominio/URL HTTPS del backend y comprobar `/health` y `/ready`.
2. Definir `NEXT_PUBLIC_API_URL` en Vercel y el origen del frontend en el motor.
3. Desplegar el código local revisado. La preparación existente incluye cambios
   sin commit: un despliegue Git no incluirá esos archivos hasta que se guarden
   y suban explícitamente al repositorio.
4. Verificar inicio y cierre de sesión, subida de DXF/DWG, finalización del
   procesamiento, SSE, exportación y persistencia tras reiniciar la API.
5. Conectar Git para despliegues automáticos después de validar la rama de
   producción. Los previews requieren un backend y base de datos separados.

Las credenciales de PostgreSQL, correo e IA pertenecen al backend. No deben
exponerse como variables `NEXT_PUBLIC_*` ni guardarse en el repositorio.

## Estado de la preparación

Publicado el 2026-10-20: `https://www.klave.space`, con API en
`https://api.klave.space`. Deployment de producción:
`dpl_7ZpDXeBhZJsS2fAoU6GDqHzGdtTB`. Build, TypeScript y 37 pruebas del cliente
pasaron; readiness y CORS del motor se verificaron. Se reparó el lockfile con
npm 11.19.0 para completar dependencias opcionales, sin cambiar versiones.
La página pública muestra el formulario para activar la primera cuenta.
Faltan el alta del administrador y la prueba autenticada de un plano.
El proyecto todavía no está conectado a Git.
