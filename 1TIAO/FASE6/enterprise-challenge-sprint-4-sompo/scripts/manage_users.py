"""Provision local accounts without putting passwords in command arguments."""

from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tractor_usage.infrastructure.auth_repository import AuthRepository
from tractor_usage.infrastructure.database import (
    Settings,
    create_database_engine,
    create_session_factory,
)


ROLES = ("ADMIN", "INSURER", "INSPECTOR", "FLEET_MANAGER")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage local preventive-inspection accounts")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--worker-id", required=True)
    create.add_argument("--role", choices=ROLES, required=True)
    create.add_argument("--fleet-id")
    access = commands.add_parser("set-role")
    access.add_argument("--worker-id", required=True)
    access.add_argument("--role", choices=ROLES, required=True)
    access.add_argument("--fleet-id")
    for name in ("reset-password", "disable", "enable"):
        commands.add_parser(name).add_argument("--worker-id", required=True)
    return parser


def _password() -> str:
    first = getpass("Password (at least 12 characters): ")
    second = getpass("Repeat password: ")
    if first != second:
        raise ValueError("passwords do not match")
    return first


def main() -> int:
    args = _parser().parse_args()
    engine = create_database_engine(Settings.from_environment().database_url)
    try:
        with create_session_factory(engine)() as session:
            repository = AuthRepository(session)
            if args.command == "create":
                principal = repository.create_user(
                    worker_id=args.worker_id,
                    password=_password(),
                    role=args.role,
                    fleet_id=args.fleet_id,
                )
                print(f"Created {principal.worker_id} ({principal.role}, id={principal.id})")
                return 0

            principal = repository.user_by_worker_id(args.worker_id)
            if principal is None:
                raise ValueError("user not found")
            if args.command == "set-role":
                updated = repository.set_access(
                    principal.id, role=args.role, fleet_id=args.fleet_id
                )
                print(f"Updated {updated.worker_id} ({updated.role}) and revoked active sessions")
            elif args.command == "reset-password":
                repository.change_password(principal.id, _password())
                print(f"Changed password for {principal.worker_id} and revoked active sessions")
            elif args.command == "disable":
                repository.disable_user(principal.id)
                print(f"Disabled {principal.worker_id} and revoked active sessions")
            else:
                repository.enable_user(principal.id)
                print(f"Enabled {principal.worker_id}")
            return 0
    except ValueError as error:
        print(f"manage-users: {error}", file=sys.stderr)
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
