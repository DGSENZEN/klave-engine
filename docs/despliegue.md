# Despliegue en producción

Para un proyecto Vercel con los servicios `web` y `app`, consulta
[Vercel Services](vercel.md). Lo siguiente describe la alternativa con VPS.

Una VPS (2 vCPU / 4 GB alcanza para un taller piloto), Docker Compose y un
dominio con dos subdominios: `app.<dominio>` (web) y `api.<dominio>` (API).
Caddy obtiene y renueva el TLS solo.

## Primera vez

1. Apunta los DNS `app.<dominio>` y `api.<dominio>` a la IP de la VPS.
2. `cp .env.example .env.prod` y llena `KLAVE_DOMAIN`,
   `KLAVE_ACME_EMAIL` y `KLAVE_USERS_DB_PASSWORD` (32 o más caracteres
   aleatorios: letras, números, `_`, `~` o `-`; Compose lo usa dentro de una URL).
   El correo (Resend o SMTP) es opcional: sin correo, los enlaces
   de invitación/recuperación se muestran al administrador para copiarlos.
3. Ejecuta `make prod-check` para validar la configuración sin mostrar secretos.
   Después, `make prod-up` construye y arranca los contenedores.
4. Abre `https://app.<dominio>` y crea la primera cuenta: es el
   administrador del taller y quien invita al resto.

El piloto usa `invite_only`: después de crear la primera cuenta, solo las
invitaciones permiten registrarse. Completa ese primer acceso antes de
compartir la URL del piloto.

Con registro abierto (`KLAVE_REGISTRATION=open`, fuera de este piloto),
cada taller es su propio espacio: al registrarse, "Crear un taller nuevo"
funda otro (quien lo crea es su administrador, activo al instante) con su
propio catálogo; registrarse sin taller pide unirse al existente y espera
aprobación. Las invitaciones entran directo al taller que invita.

`KLAVE_ENV=production` hace dos cosas: solo los orígenes configurados pueden
llamar a la API con credenciales (nada de `localhost`), y el arranque
**falla con un mensaje claro** si la configuración está a medias (origen en
localhost, cookie sin `Secure`, credenciales de desarrollo en la base de
usuarios).

## Piloto privado (solo por invitación)

Para que un grupo cerrado (cofundadores, un taller piloto) pruebe desde cero
sin que nadie más pueda registrarse:

1. En `.env.prod`: `KLAVE_REGISTRATION=invite_only`. El registro sin invitación
   se rechaza; la pantalla de entrada lo dice.
   Sin correo configurado, cada enlace se muestra en pantalla para copiarlo.
2. Arranca con `make prod-up`. El volumen `klave-data` nace vacío: no copies
   tu `data/` local si quieres que prueben en limpio.
3. Abre la web y crea la primera cuenta de administrador. Esta es la única
   excepción a `invite_only`: en cuanto existe una cuenta, el registro
   público queda cerrado. También puedes preparar un taller y una invitación
   administrativa desde el contenedor:

   ```bash
   docker compose -f docker-compose.prod.yml --env-file .env.prod exec api \
     .venv/bin/python -m apps.api.auth.cli create-workspace piloto "Taller piloto"
   docker compose -f docker-compose.prod.yml --env-file .env.prod exec api \
     .venv/bin/python -m apps.api.auth.cli invite-admin piloto tu@correo.mx
   ```

   Imprime `https://app.<dominio>/invitacion?token=…` (válido 7 días).
4. Si usaste la CLI, abre el enlace y crea tu cuenta de administrador. Desde `/equipo`
   invita a cada persona; el enlace de cada invitación aparece en la misma
   pantalla y se manda por el canal que sea.
5. Lo demás sigue igual: `make prod-logs` para ver qué pasa, `make backup-now`
   antes de cualquier cambio grande.

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
`users.dump` (pg_dump del users-db), `sqlite.tar.gz` (copias en línea de
los catálogos SQLite) y `data.tar.gz` (uploads, defaults y demás archivos) bajo `/backups/<stamp>/`, y borra lo más viejo que
`BACKUP_KEEP_DAYS` (14 por defecto). **El volumen `backups` vive en la misma
máquina: cópialo afuera** (rsync/rclone a otro lugar) para que un disco
muerto no se lleve todo.

- Respaldo manual: `docker compose -f docker-compose.prod.yml --env-file .env.prod exec backup sh /backup.sh once`
- Verificar: `docker compose -f docker-compose.prod.yml --env-file .env.prod exec backup sh /backup.sh restore <stamp>`
  verifica la integridad y muestra instrucciones; no restaura ni cambia datos.

Para una restauración manual, copia primero el directorio completo fuera del
servidor y verifícalo en un entorno aislado con PostgreSQL 16 y Python 3:

```bash
python3 deploy/backup.py verify /ruta/privada/RESPALDO
createdb klave_restore_prueba
pg_restore --exit-on-error --no-owner --no-acl --dbname=klave_restore_prueba /ruta/privada/RESPALDO/users.dump
mkdir /ruta/nueva/klave-restore-data
tar -xzf /ruta/privada/RESPALDO/sqlite.tar.gz -C /ruta/nueva/klave-restore-data
tar -xzf /ruta/privada/RESPALDO/data.tar.gz -C /ruta/nueva/klave-restore-data
```

Usa una base y un directorio nuevos: `createdb` y `mkdir` deben fallar si ya
existen. Arranca la versión correspondiente del API con esos recursos aislados
y verifica acceso, catálogo, planos y exportación antes de cualquier cambio
de producción. El simulacro completo de restauración y rollback sigue pendiente;
las pruebas de integridad del respaldo no demuestran ese recorrido.

Nota: `apps/web/package-lock.json` debe regenerarse dentro de Linux
(`docker run --rm -v $PWD/apps/web:/w -w /w node:24-alpine npm install
--package-lock-only`) cuando cambien dependencias, para que incluya los
opcionales de todas las plataformas y `npm ci` funcione en la imagen.

## Comprobar una versión antes de publicarla

En una máquina de desarrollo con Python/uv, Node 24 y Docker Compose:

```bash
uv sync --frozen
npm --prefix apps/web ci
make users-db-up
make release-check                 # usa .env.prod, no imprime sus valores
# Otro archivo: make release-check ENV_FILE=/ruta/al/piloto.env
```

El chequeo exige el PostgreSQL local de pruebas (puerto 5433), valida el
piloto por invitación y Compose, y ejecuta Ruff, mypy, toda la suite Python,
las pruebas del cliente, ESLint y el build de producción. El build usa
`https://api.<KLAVE_DOMAIN>`; cambiar el dominio requiere reconstruir la web.
`make prod-check` solo valida las variables y no necesita Docker ni la base.
`.env.prod` y sus copias están excluidos de Git.

Este comando no publica nada ni prueba DNS, TLS o restauración del servidor.
Después de arrancar en la VPS, comprueba `/health`, crea la primera cuenta,
invita a otro usuario, sube un plano, revisa el avance y exporta un presupuesto.
Haz un respaldo manual y restaura una copia en un entorno separado antes de
recibir planos de los usuarios. Mantén una copia del respaldo fuera de la VPS.

## Actualizar

```bash
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Las migraciones del catálogo corren solas al abrir cada base; las
del users-db corren al arrancar la API.

## Sin Docker (desarrollo)

Como siempre: `make users-db-up`, `uv run uvicorn apps.api.main:app`,
`npm --prefix apps/web run dev`. `KLAVE_ENV` sin definir = modo dev.
Para esos procesos separados, define `NEXT_PUBLIC_API_URL=http://localhost:8000`
en `.env`; con Vercel Services deja ese override sin definir y usa
`vercel dev -L` desde la raíz.
