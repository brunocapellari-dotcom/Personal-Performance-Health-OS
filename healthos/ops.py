from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

from .audit import verify_audit_chain
from .backup import export_backup, restore_backup
from .config import Settings
from .db import Database


def _write_private_atomic(destination: Path, payload: bytes) -> None:
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def backup_command(destination: Path) -> None:
    settings = Settings.from_env()
    settings.validate()
    database = Database(settings)
    with database.session() as db:
        payload = export_backup(db, settings)
    _write_private_atomic(destination, payload)
    print(f"encrypted backup written: {destination}")


def restore_command(source: Path, *, destructive: bool) -> None:
    if not destructive:
        raise SystemExit("restore requires --destructive")
    settings = Settings.from_env()
    settings.validate()
    database = Database(settings)
    payload = source.expanduser().read_bytes()
    with database.session() as db:
        restore_backup(db, settings, payload, destructive=True)
    print("restore completed and audit chain verified")


def verify_command() -> None:
    settings = Settings.from_env()
    settings.validate()
    database = Database(settings)
    with database.session() as db:
        valid = verify_audit_chain(db, settings)
    if not valid:
        raise SystemExit("audit chain verification failed")
    print("audit chain valid")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="healthos-ops")
    commands = parser.add_subparsers(dest="command", required=True)

    backup_parser = commands.add_parser("backup", help="write encrypted database backup")
    backup_parser.add_argument("destination", type=Path)

    restore_parser = commands.add_parser("restore", help="restore an encrypted backup")
    restore_parser.add_argument("source", type=Path)
    restore_parser.add_argument("--destructive", action="store_true")

    commands.add_parser("audit-verify", help="verify the chained audit log")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "backup":
        backup_command(args.destination)
    elif args.command == "restore":
        restore_command(args.source, destructive=args.destructive)
    elif args.command == "audit-verify":
        verify_command()
    else:  # pragma: no cover - argparse constrains this branch
        raise SystemExit(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
