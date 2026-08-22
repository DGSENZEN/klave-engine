"""Operator commands for the users database.

    uv run python -m apps.api.auth.cli list-workspaces
    uv run python -m apps.api.auth.cli create-workspace <slug> "<Nombre>"
    uv run python -m apps.api.auth.cli invite-admin <slug> <email>

One taller per deployment is the default; ``create-workspace`` lets several
share the same server, and ``invite-admin`` prints the bootstrap link for the
new workspace's first administrator (invitations are the only way in).
"""

import argparse
import sys

from klave_engine.common.config import get_settings

from apps.api.auth.common import web_link
from apps.api.auth.store import UsersDbUnavailable, get_user_store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="klave-auth")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list-workspaces")
    create = sub.add_parser("create-workspace")
    create.add_argument("slug")
    create.add_argument("name")
    invite = sub.add_parser("invite-admin")
    invite.add_argument("slug")
    invite.add_argument("email")
    args = parser.parse_args(argv)

    settings = get_settings()
    users = get_user_store(settings.users_database_url)
    try:
        if args.command == "list-workspaces":
            for row in users.list_workspaces():
                print(f"{row['slug']:<20} {row['name']:<30} usuarios: {row['user_count']}")
        elif args.command == "create-workspace":
            row = users.create_workspace(args.slug, args.name)
            print(f"Taller creado: {row['slug']} ({row['name']})")
        elif args.command == "invite-admin":
            workspace = users.get_workspace_by_slug(args.slug)
            if workspace is None:
                print(f"No existe el taller {args.slug}", file=sys.stderr)
                return 1
            if users.get_by_email(args.email):
                print("Ese correo ya tiene cuenta.", file=sys.stderr)
                return 1
            _, token = users.create_invitation(
                workspace_id=str(workspace["workspace_id"]), email=args.email,
                role="admin", project_grants=[], invited_by=None,
            )
            users.record_audit(
                workspace_id=str(workspace["workspace_id"]), actor=None,
                action="invitation_created", target_type="invitation", target_id=None,
                detail={"email": args.email, "role": "admin", "via": "cli"},
            )
            print("Enlace de invitación (válido 7 días):")
            print(web_link(settings, f"/invitacion?token={token}"))
    except UsersDbUnavailable:
        print(
            "La base de datos de usuarios no está disponible (make users-db-up).",
            file=sys.stderr,
        )
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
