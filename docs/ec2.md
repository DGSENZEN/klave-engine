# EC2 backend for www.klave.space

This setup runs PostgreSQL, FastAPI with its DWG converter, Caddy for HTTPS,
and local backups on one EC2 instance. Next.js stays on Vercel. The engine
has one Uvicorn process and processes one drawing job at a time initially;
measure memory and processing time before increasing concurrency.

Keep instance addresses, SSH keys and release records in the operator's
private deployment configuration. The steps below describe a fresh setup;
for upgrades, use the tested release procedure in [CI/CD](cicd.md).

## 1. Find the instance and prepare DNS

In AWS → EC2 → Instances, select the running instance. Record its public IPv4,
instance type and operating system. The commands below support Ubuntu 24.04
or 26.04 on x86_64 (the installed host uses 26.04). If it uses Amazon Linux,
use that OS's installation instructions
instead. Do not launch a second instance just to change the configuration.

Use a stable public IP for DNS. An EC2 auto-assigned public IPv4 can change
after stop/start; an Elastic IP stays fixed while allocated. Both public IP
types incur AWS IPv4 charges. If using an Elastic IP, associate it with this
instance and avoid leaving an additional address allocated but unused.

At the DNS provider for `klave.space`, create:

| Type | Name | Value |
|---|---|---|
| A | `api` | The EC2 public IPv4 address |

Leave `www` pointing at Vercel. Start with DNS-only mode if the provider
offers a proxy. Remove conflicting `api` A/AAAA records. No second domain
purchase is necessary. Check `dig +short api.klave.space` from your computer.

Configure EC2 Security Group inbound rules:

| Port | Source initially |
|---|---|
| TCP 22 / SSH | My IP only |
| TCP 80 / HTTP | Anywhere IPv4, for certificate issuance |
| TCP 443 / HTTPS | My IP only, until the first administrator exists |

Do not open 5432 or 8000. Docker publishes only Caddy's 80/443; the database
and API communicate on its internal network. After bootstrap, open 443 to
the intended users (Anywhere IPv4 for public access). The initial IP limit
matters because the app permits registration of its first account.

## 2. Connect and install Docker

On your Mac, substitute the actual key path and IP:

```bash
chmod 600 /path/to/klave-key.pem
ssh -i /path/to/klave-key.pem ubuntu@EC2_PUBLIC_IP
```

On the EC2 Ubuntu server, install Docker from its official apt repository:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
sudo docker compose version
mkdir -p ~/klave-engine
```

Reference: <https://docs.docker.com/engine/install/ubuntu/>.

## 3. Copy the current backend source

On your Mac, in the repository root, package only backend source and deployment
files. This excludes your local environment files, customer drawings and
frontend build output. Replace the key path and IP before running `scp`.

```bash
tar --exclude='__pycache__' --exclude='.DS_Store' --exclude='.env*' \
  -czf /tmp/klave-ec2-source.tar.gz \
  apps/api apps/__init__.py packages pyproject.toml uv.lock README.md \
  .dockerignore docker-compose.ec2.yml deploy/Caddyfile.ec2 \
  deploy/ec2.env.example deploy/backup.Dockerfile deploy/backup.py deploy/backup.sh
scp -i /path/to/klave-key.pem /tmp/klave-ec2-source.tar.gz ubuntu@EC2_PUBLIC_IP:~/
```

On the server:

```bash
tar -xzf ~/klave-ec2-source.tar.gz -C ~/klave-engine
cd ~/klave-engine
cp deploy/ec2.env.example .env.prod
chmod 600 .env.prod
openssl rand -hex 24
nano .env.prod
```

Set `KLAVE_USERS_DB_PASSWORD` to the generated hex password, and replace
`KLAVE_ACME_EMAIL` with your email. Keep the password in your password manager.
Do not send it in chat. Defaults already use `api.klave.space` and
`https://www.klave.space`. This copy command is for a fresh installation;
preserve the existing `.env.prod` during upgrades. Changing the password in
the file does not change an already initialized PostgreSQL volume's password.

## 4. Start the database and backend

On the server, define a shell helper to keep the Compose project and file
selection consistent. Define it again in each new SSH session:

```bash
cd ~/klave-engine
dc() { sudo docker compose -p klave -f docker-compose.ec2.yml --env-file .env.prod "$@"; }
dc config --quiet
dc up -d --build users-db api
dc ps
dc exec api curl -fsS http://127.0.0.1:8000/ready
```

The first build compiles LibreDWG and can take several minutes. Wait for the
API to be healthy; retry the readiness command if initialization is still
running. If the build or readiness check fails, inspect `dc logs --tail=100 api`.
Do not start the public proxy until database and storage readiness both pass.

Leave `KLAVE_CONVERTER_EXECUTABLE_PATH` unset for this image. That setting
selects the ODA directory-conversion adapter, whose arguments do not work
with LibreDWG. The bundled `dwg2dxf` is detected on PATH and uses the engine's
single-file LibreDWG adapter automatically. For an earlier EC2 configuration
that set this variable in the API environment, remove the mapping from
`docker-compose.ec2.yml` and recreate only the API with `dc up -d --no-deps api`.
No image rebuild or volume removal is needed.

After DNS resolves to the instance and readiness succeeds:

```bash
dc up -d caddy backup
curl -fsS https://api.klave.space/health
curl -fsS https://api.klave.space/ready
```

The HTTPS tests should be run from your Mac while 443 is limited to My IP;
the EC2 server's own outbound public IP is not necessarily allowed by that
rule. Caddy uses the HTTP challenge on port 80 to obtain its certificate.

## 5. Connect Vercel and create the administrator

In Vercel → `klave-web` → Settings → Domains, connect `www.klave.space` if
not already connected. Follow Vercel's DNS instructions for `www` only.
Set these production environment variables:

```text
KLAVE_LOAD_DOTENV=0
NEXT_PUBLIC_API_URL=https://api.klave.space
```

Build and deploy the reviewed current frontend source. The API URL is baked
into the browser bundle, so changing the variable requires a new deployment.
Record deployment identifiers in the hosting dashboard or private release
records. See [Vercel production notes](vercel-production.md).

While EC2 port 443 is still restricted to your IP, open
`https://www.klave.space` and register the first administrator. Then widen
the 443 rule for your users. Registration is invitation-only after the first
account. Cookies stay on the API host and use Secure + SameSite=Lax; both
app and API must use HTTPS under `klave.space` for this setup.

Test login/logout, a small DXF, a representative DWG, processing progress,
live events and an export. Restart only the API with `dc restart api` and
check that the account and completed project still exist.

## 6. Back up and monitor

```bash
dc exec backup sh /backup.sh once
dc logs --tail=50 backup
df -h
```

The backup container takes an initial snapshot, then runs daily at 03:00 UTC
(21:00 the previous day in Mérida). Completed backups are retained for seven
days in the `backups` volume. Disk consumption depends on drawing sizes and
retention; 30 GiB may need expansion as the pilot grows.

For a quiesced snapshot before an upgrade, finish pending jobs, stop API
writes with `dc stop api`, run the backup command, then `dc start api`.
Copy a completed snapshot off the instance, for example to your computer:

```bash
# Server: use the stamp printed by the backup command.
mkdir -p ~/klave-backup-export
dc cp backup:/backups/COMPLETED_STAMP ~/klave-backup-export/
```

```bash
# Mac: substitute the real key, public IP and stamp.
scp -r -i /path/to/klave-key.pem \
  ubuntu@EC2_PUBLIC_IP:~/klave-backup-export/COMPLETED_STAMP ./
```

A same-server backup does not protect against losing or deleting the EC2 disk.
Test recovery separately before accepting real customer work. Never run
`dc down -v`: it deletes the database, project files and backup volumes.

Check AWS Billing → Free Tier for credit balance and expiry. EC2, EBS,
public IPv4, snapshots and excess transfer consume the available allowance.
Optional AI/email providers have separate billing. Confirm the Free plan
status; a budget alert alone does not stop spending on a Paid account.
