# Despliegue en producción

Una VPS (2 vCPU / 4 GB alcanza para un taller piloto), Docker Compose y un
dominio con dos subdominios: `app.<dominio>` (web) y `api.<dominio>` (API).
Caddy obtiene y renueva el TLS solo.

## Primera vez

1. Apunta los DNS `app.<dominio>` y `api.<dominio>` a la IP de la VPS.
2. `cp .env.example .env.prod` y llena `KLAVE_DOMAIN`,
   `KLAVE_ACME_EMAIL` y `KLAVE_USERS_DB_PASSWORD` (largo y aleatorio).
   Correo (Resend o SMTP) y Google son opcionales: sin correo, los enlaces
   de invitación/recuperación se muestran al administrador para copiarlos.
3. `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`
4. Abre `https://app.<dominio>` y crea la primera cuenta: es el
   administrador del taller y quien invita al resto.

Cada taller es su propio espacio: al registrarse, "Crear un taller nuevo"
funda otro (quien lo crea es su administrador, activo al instante) con su
propio catálogo; registrarse sin taller pide unirse al existente y espera
aprobación. Las invitaciones entran directo al taller que invita.

`KLAVE_ENV=production` hace dos cosas: solo los orígenes configurados pueden
llamar a la API con credenciales (nada de `localhost`), y el arranque
**falla con un mensaje claro** si la configuración está a medias (origen en
localhost, cookie sin `Secure`, credenciales de desarrollo en la base de
usuarios).

## Qué corre

| Servicio | Imagen | Notas |
|---|---|---|
| `caddy` | caddy:2 | TLS automático; SSE sin buffering; cuerpo hasta 120 MB |
| `web` | `apps/web/Dockerfile` | Next.js standalone; `NEXT_PUBLIC_API_URL` se hornea al construir |
| `api` | `apps/api/Dockerfile` | uvicorn sin `--reload`, `dwg2dxf` 0.13.3 (LibreDWG compilado de fuente — Debian no lo empaqueta), healthcheck `/health` |
| `users-db` | postgres:16 | cuentas, sesiones, permisos; solo en la red interna |
| `backup` | postgres:16 | respaldo diario ~03:00 UTC al volumen `backups` |

Los datos viven en volúmenes con nombre: `klave-data` (uploads y un
catálogo por taller), `users-db-data`, `backups`, `caddy-data`.

## Respaldos y restauración (probados)

El servicio `backup` corre `deploy/backup.sh`: cada noche guarda
`users.dump` (pg_dump del users-db) y `data.tar.gz` (uploads, catálogos,
defaults) bajo `/backups/<stamp>/`, y borra lo más viejo que
`BACKUP_KEEP_DAYS` (14 por defecto). **El volumen `backups` vive en la misma
máquina: cópialo afuera** (rsync/rclone a otro lugar) para que un disco
muerto no se lleve todo.

- Respaldo manual: `docker compose -f docker-compose.prod.yml exec backup sh /backup.sh once`
- Restaurar: `sh deploy/backup.sh restore <stamp>` imprime los pasos exactos
  (parar api/web, `pg_restore --clean`, extraer el tar al volumen, arrancar).

El ciclo respaldo → restauración está probado: el dump restaura las 47
tablas/objetos del users-db y el tar restaura los catálogos por taller con
sus aliases intactos.

Nota: `apps/web/package-lock.json` debe regenerarse dentro de Linux
(`docker run --rm -v $PWD/apps/web:/w -w /w node:24-alpine npm install
--package-lock-only`) cuando cambien dependencias, para que incluya los
opcionales de todas las plataformas y `npm ci` funcione en la imagen.

## Actualizar

```bash
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Las migraciones del catálogo (v2→v14) corren solas al abrir cada base; las
del users-db corren al arrancar la API.

## Sin Docker (desarrollo)

Como siempre: `make users-db-up`, `uv run uvicorn apps.api.main:app`,
`npm --prefix apps/web run dev`. `KLAVE_ENV` sin definir = modo dev.
