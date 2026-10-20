# Vercel: un proyecto, dos servicios

La configuración de `vercel.json` define `app` (FastAPI desde la raíz del
repositorio) y `web` (Next.js desde `apps/web`). La entrada de Python es
`apps.api.main:app`; la raíz conserva `pyproject.toml`, `uv.lock` y el paquete
`packages/klave_engine`, que no están dentro de `apps/api`.

## Rutas y binding

| Entrada pública | Destino |
|---|---|
| `/`, páginas, recursos Next.js | `web` |
| `/api/*` | Route Handler de `web` → binding → `app` |
| Acceso directo a `app` | Sin rewrite público; servicio interno |

El único rewrite público es el catch-all hacia `web`. La ruta
`apps/web/app/api/[[...path]]/route.ts` quita `/api` y reenvía a FastAPI:
`/api/projects` llega como `/projects`. Reenvía sesión, Origin, archivos,
descargas y SSE; conserva los errores del backend y evita cachear datos de
usuario. El backend sigue aplicando autenticación, permisos y CSRF: un
binding permite comunicación interna, no autoriza al usuario.

`web` declara un binding hacia `app` que Vercel inyecta como `KLAVE_APP_URL`.
No crees esa variable manualmente, no la publiques con `NEXT_PUBLIC_`, ni la
uses en `next.config.ts`, middleware o durante el build. Se lee dentro de la
función que atiende cada petición. `app` no llama a `web`, por lo que no
necesita un binding de vuelta. Los enlaces al frontend son URLs públicas,
no llamadas internas entre servicios.

Referencias: [Services](https://vercel.com/docs/services),
[bindings](https://vercel.com/docs/services/bindings).

## Configuración del proyecto

1. Importa el repositorio como **un proyecto** y deja Root Directory en `.`.
   Los frameworks y sus directorios ya se declaran por servicio.
2. Mantén los comandos de instalación y build predeterminados por framework;
   no añadas overrides globales de Next.js a este proyecto de dos servicios.
3. Configura las variables siguientes en Vercel para cada entorno:

| Variable | Valor |
|---|---|
| `KLAVE_LOAD_DOTENV` | `0` |
| `KLAVE_ENV` | `production` |
| `KLAVE_WEB_ORIGIN` | Origen público exacto, por ejemplo `https://klave.example` |
| `KLAVE_API_PUBLIC_PREFIX` | `/api` |
| `KLAVE_USERS_DATABASE_URL` | Conexión de PostgreSQL administrado; nunca credenciales locales |
| `KLAVE_REGISTRATION` | `invite_only` |
| `KLAVE_COOKIE_SECURE` | `true` |
| `KLAVE_COOKIE_SAMESITE` | `lax` |

Deja `NEXT_PUBLIC_API_URL` y `KLAVE_COOKIE_DOMAIN` sin definir: el navegador
usa `/api` y cookies del mismo dominio. No reutilices un override público que
apunte a localhost o al hostname de Docker. Para Google, registra
`<KLAVE_WEB_ORIGIN>/api/auth/google/callback` y configura sus credenciales.
Correo y proveedores de IA son opcionales, con las mismas variables de
`.env.example`. Los archivos `.env`, datos y artefactos locales se excluyen
de la carga con `.vercelignore`; las credenciales se gestionan en Vercel.

Los previews necesitan su propio origen permitido y una base de datos
separada; no conectes previews de ramas a las cuentas o datos de producción.
No se añade un comodín de orígenes `*.vercel.app`. Verifica también que las
URLs públicas de invitación y recuperación apunten al entorno correcto.

## Probar en local

Instala una versión de Vercel CLI compatible con Services y `uv >= 0.9.25`
(mínimo exigido por el builder Python de CLI 64.7.0). Desde la raíz:

```bash
uv sync --frozen
npm --prefix apps/web ci
vercel dev -L
```

`-L` usa modo local sin vincular una cuenta cloud. Vercel inicia los servicios
e inyecta el binding; no lo sustituyas por una URL fija. Si tu `.env` tiene
`NEXT_PUBLIC_API_URL`, elimina ese override para probar el proxy. En local,
usa `KLAVE_ENV=dev`, `KLAVE_WEB_ORIGIN` con el puerto público de `vercel dev`,
`KLAVE_API_PUBLIC_PREFIX=/api` y el PostgreSQL dedicado de desarrollo. No
uses `KLAVE_COOKIE_SECURE=true` para probar sobre HTTP.

Comprueba `/` (web), `/api/health` (API), `/api/ready` (base y almacenamiento),
inicio/cierre de sesión, subida, avance y exportación. `/health` sin `/api`
pertenece al frontend, no debe exponer FastAPI. La prueba de routing local
no sustituye la prueba de durabilidad y procesamiento en cloud.

## Lo que esta configuración todavía no resuelve

Los servicios y el proxy preparan el despliegue conjunto. **El motor actual
todavía necesita adaptación antes de recibir datos reales en Vercel**:

- Los proyectos, registros JSON, resultados y catálogos SQLite viven en el
  filesystem. Hay que moverlos a almacenamiento durable compartido y una
  base adecuada. `/tmp` permite previews desechables, no persistencia.
- El scheduler usa threads y el bus SSE vive en memoria de un proceso. Hay
  que externalizar jobs, estado y eventos para soportar reinicios y varias
  instancias. El servicio FastAPI no convierte estos threads en trabajo
  durable al terminar una petición.
- Las subidas pasan por funciones: los límites de payload de Vercel pueden
  ser menores que los 100 MB por archivo que admite hoy la aplicación.
  Los archivos grandes necesitan subida directa a almacenamiento y posterior
  procesamiento; el proxy no elimina esos límites.
- La configuración usa el runtime Python, no el Dockerfile que compila
  `dwg2dxf`. Para DWG hay que empaquetar el conversor en un runtime compatible
  o separar la conversión. DXF no requiere ese ejecutable.

Consulta [filesystem](https://vercel.com/docs/functions/runtimes),
[límites de Functions](https://vercel.com/docs/functions/limitations) y
[Daemons](https://vercel.com/docs/daemons). No se seleccionan proveedores
de almacenamiento ni se crean recursos facturables con este cambio.
