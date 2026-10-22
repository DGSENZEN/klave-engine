"""Validate a private pilot's Compose settings without displaying credentials.

Config only: uv run python scripts/release_check.py --env-file .env.prod
Full checks: make release-check (needs Docker, Node 24, and make users-db-up).
"""

import argparse
import ipaddress
import os
import re
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def validate(values: dict[str, str | None]) -> list[str]:
    errors = []
    domain = values.get("KLAVE_DOMAIN") or ""
    label = r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    try:
        ipaddress.ip_address(domain)
        is_ip = True
    except ValueError:
        is_ip = False
    if (
        not re.fullmatch(rf"{label}(?:\.{label})+", domain)
        or len(domain) > 245
        or domain.endswith((".localhost", ".local", ".test"))
        or is_ip
    ):
        errors.append("KLAVE_DOMAIN: define un dominio público sin https://, puerto ni ruta.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", values.get("KLAVE_ACME_EMAIL") or ""):
        errors.append("KLAVE_ACME_EMAIL: define el correo para los certificados TLS.")
    # Compose inserts this value directly in a PostgreSQL URL. Require a
    # URL-safe password so reserved characters cannot change the URL's meaning.
    password = values.get("KLAVE_USERS_DB_PASSWORD") or ""
    if len(password) < 32 or not re.fullmatch(r"[A-Za-z0-9_~-]+", password):
        errors.append(
            "KLAVE_USERS_DB_PASSWORD: usa 32+ caracteres aleatorios (letras, números, _, ~ o -)."
        )
    if (values.get("KLAVE_REGISTRATION") or "invite_only") != "invite_only":
        errors.append("KLAVE_REGISTRATION: el piloto privado requiere invite_only.")
    days = values.get("BACKUP_KEEP_DAYS") or "14"
    if not days.isdigit() or int(days) < 1:
        errors.append("BACKUP_KEEP_DAYS: debe ser un entero positivo.")
    if (values.get("KLAVE_COOKIE_SAMESITE") or "lax") not in {"lax", "strict", "none"}:
        errors.append("KLAVE_COOKIE_SAMESITE: usa lax, strict o none.")
    return errors


def run_stage(name: str, argv: list[str], *, env: dict[str, str], cwd: Path) -> int:
    """Run a required stage without leaking credentials into logs."""
    print(f"→ {name}", flush=True)
    try:
        result = subprocess.run(
            argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=1800,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print(f"Stage {name}: unavailable or timed out.", file=sys.stderr)
        return 1
    output = result.stdout + result.stderr
    for key, value in env.items():
        if value and len(value) >= 4 and any(
            word in key.upper() for word in ("PASSWORD", "SECRET", "TOKEN", "KEY", "DATABASE_URL")
        ):
            output = output.replace(value, "[redacted]")
    output = re.sub(r"(?i)(token|password|code)=([^&\s\"']+)", r"\1=[redacted]", output)
    if output:
        print(output[-16000:], end="" if output.endswith("\n") else "\n")
    if result.returncode:
        print(f"Stage {name}: failed ({result.returncode}).", file=sys.stderr)
    return result.returncode


def stage_commands(state_dir: Path) -> list[tuple[str, list[str]]]:
    python = sys.executable
    return [
        ("ruff", [python, "-m", "ruff", "check", "."]),
        ("mypy", [python, "-m", "mypy", "packages/klave_engine"]),
        ("python", [python, "-m", "pytest"]),
        ("client", ["npm", "--prefix", "apps/web", "test"]),
        ("lint", ["npm", "--prefix", "apps/web", "run", "lint"]),
        ("typecheck", ["npm", "--prefix", "apps/web", "run", "typecheck"]),
        ("synthetic-eval", [python, str(ROOT / "scripts/release_check.py"),
                            "--synthetic-eval", str(state_dir)]),
        ("browser-build", ["npm", "--prefix", "apps/web", "run", "build"]),
        ("browser", ["npm", "--prefix", "apps/web", "run", "test:e2e"]),
        ("production-build", ["npm", "--prefix", "apps/web", "run", "build"]),
        ("backup-ops-build", ["docker", "build", "-f", "deploy/backup-ops.Dockerfile",
                              "-t", "klave-backup-ops:verify", "."]),
        ("backup-ops-tools", ["docker", "run", "--rm", "--network", "none",
                              "--entrypoint", "aws", "klave-backup-ops:verify", "s3api",
                              "put-object", "--generate-cli-skeleton", "input"]),
        ("container-build", [python, "deploy/smoke.py", "build", "--state-dir", str(state_dir)]),
        ("container-check", [python, "deploy/smoke.py", "check", "--state-dir", str(state_dir)]),
    ]


def run_synthetic_eval(state_dir: Path) -> int:
    from klave_engine.evals.regression_suite import run_regression_suite

    summary = run_regression_suite(
        project_root=state_dir / "demo", reports_dir=state_dir / "reports",
    )
    return 0 if summary["all_passed"] else 1


def main() -> int:
    import tempfile

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env.prod")
    parser.add_argument("--run", action="store_true", help="Run all required release checks.")
    parser.add_argument("--require-gold", action="store_true")
    parser.add_argument("--synthetic-eval", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.synthetic_eval:
        return run_synthetic_eval(args.synthetic_eval)
    if not args.env_file.is_file():
        print("Falta configuración: copia .env.example a .env.prod y edítalo.", file=sys.stderr)
        return 1
    values = dict(dotenv_values(args.env_file, interpolate=False))
    errors = validate(values)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("Configuración del piloto privado: válida.", flush=True)
    if not args.run:
        return 0
    import psycopg

    try:
        with psycopg.connect(
            "postgresql://klave_users:klave@127.0.0.1:5433/klave_users", connect_timeout=2,
        ):
            pass
    except psycopg.OperationalError:
        print("Falta PostgreSQL de pruebas: ejecuta make users-db-up.", file=sys.stderr)
        return 1
    compose_env = {**os.environ, **{k: v for k, v in values.items() if v is not None}}
    code = run_stage("compose-config", [
        "docker", "compose", "-f", str(ROOT / "docker-compose.prod.yml"),
        "--env-file", str(args.env_file.resolve()), "config", "--quiet",
    ], env=compose_env, cwd=ROOT)
    if code:
        return code
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("KLAVE_", "NEXT_PUBLIC_"))
           and k not in {"ANTHROPIC_API_KEY", "GEMINI_API_KEY"}}
    env.update({"KLAVE_LOAD_DOTENV": "0", "ANTHROPIC_API_KEY": "", "GEMINI_API_KEY": ""})
    production_url = f"https://api.{values['KLAVE_DOMAIN']}"
    with tempfile.TemporaryDirectory(prefix="klave-release-") as temporary:
        state_dir = Path(temporary)
        try:
            for name, command in stage_commands(state_dir):
                stage_env = {**env, "NEXT_PUBLIC_API_URL": (
                    production_url if name == "production-build" else "http://127.0.0.1:18000"
                )}
                code = run_stage(name, command, env=stage_env, cwd=ROOT)
                if code:
                    return code
        finally:
            if (state_dir / "smoke.json").exists():
                run_stage("container-cleanup", [
                    sys.executable, "deploy/smoke.py", "cleanup", "--state-dir", str(state_dir),
                ], env=env, cwd=ROOT)
        if args.require_gold:
            from klave_engine.evals.gold import run

            summary = run(reports_dir=state_dir / "gold-reports")
            if not summary["all_passed"] or summary["unavailable"] or not summary["entries"]:
                print("Private gold evaluation failed or fixtures unavailable.", file=sys.stderr)
                return 1
        else:
            print("Private gold: outstanding; run --require-gold on the fixture-bearing machine.")
    print("Automated checks complete. Cloud and observed customer acceptance remain outstanding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
