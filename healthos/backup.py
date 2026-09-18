from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, func, select, text
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session

from .audit import verify_audit_chain
from .config import Settings
from .models import (
    AuditLogModel,
    AuthChallengeModel,
    ChangeLogModel,
    DeviceModel,
    EntityRecordModel,
    PlanSnapshotModel,
)

MAGIC = b"HOSB1"
MODELS = (
    DeviceModel,
    AuthChallengeModel,
    EntityRecordModel,
    ChangeLogModel,
    AuditLogModel,
    PlanSnapshotModel,
)
DELETE_ORDER = tuple(reversed(MODELS))


def export_backup(db: Session, settings: Settings) -> bytes:
    key = settings.backup_key()
    if key is None:
        raise RuntimeError("backup encryption key is not configured")
    tables: dict[str, list[dict[str, Any]]] = {}
    for model in MODELS:
        rows = db.scalars(select(model)).all()
        tables[model.__tablename__] = [_row_to_dict(row) for row in rows]
    payload = json.dumps(
        {"version": 1, "tables": tables},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, payload, MAGIC)
    return MAGIC + nonce + ciphertext


def restore_backup(db: Session, settings: Settings, backup: bytes, *, destructive: bool = False) -> None:
    if not destructive:
        raise PermissionError("restore requires destructive=True")
    snapshot = _decrypt_backup(settings, backup)
    if snapshot.get("version") != 1:
        raise ValueError("unsupported backup version")
    tables = snapshot.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("backup tables are invalid")

    for model in DELETE_ORDER:
        db.execute(delete(model))
    db.flush()

    by_table = {model.__tablename__: model for model in MODELS}
    for table_name, model in by_table.items():
        raw_rows = tables.get(table_name, [])
        if not isinstance(raw_rows, list):
            raise ValueError(f"backup table {table_name} is invalid")
        for raw_row in raw_rows:
            if not isinstance(raw_row, dict):
                raise ValueError(f"backup row in {table_name} is invalid")
            db.add(model(**{key: _decode_value(value) for key, value in raw_row.items()}))
        db.flush()

    if db.bind is not None and db.bind.dialect.name == "postgresql":
        _reset_postgres_sequence(db, "change_log", "server_seq")
        _reset_postgres_sequence(db, "audit_log", "audit_seq")
    if not verify_audit_chain(db, settings):
        raise ValueError("restored audit chain verification failed")


def _decrypt_backup(settings: Settings, backup: bytes) -> dict[str, Any]:
    key = settings.backup_key()
    if key is None:
        raise RuntimeError("backup encryption key is not configured")
    if len(backup) <= len(MAGIC) + 12 or not backup.startswith(MAGIC):
        raise ValueError("invalid backup envelope")
    nonce_start = len(MAGIC)
    nonce = backup[nonce_start : nonce_start + 12]
    ciphertext = backup[nonce_start + 12 :]
    clear = AESGCM(key).decrypt(nonce, ciphertext, MAGIC)
    decoded = json.loads(clear)
    if not isinstance(decoded, dict):
        raise ValueError("backup payload must be an object")
    return decoded


def _row_to_dict(row: object) -> dict[str, Any]:
    mapper = inspect(row).mapper
    return {column.key: _encode_value(getattr(row, column.key)) for column in mapper.column_attrs}


def _encode_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return {"$healthos_type": "datetime", "value": value.isoformat()}
    return value


def _decode_value(value: Any) -> Any:
    if isinstance(value, dict) and value.get("$healthos_type") == "datetime":
        return datetime.fromisoformat(str(value["value"]))
    return value


def _reset_postgres_sequence(db: Session, table: str, column: str) -> None:
    max_value = int(db.scalar(text(f"SELECT COALESCE(MAX({column}), 0) FROM {table}")) or 0)
    if max_value == 0:
        db.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', '{column}'), 1, false)"))
    else:
        db.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}', '{column}'), :value, true)"), {"value": max_value})
