from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .auth import canonical_json, sha256_hex
from .config import Settings
from .models import AuditLogModel

_GENESIS_HASH = "0" * 64


def append_audit(
    db: Session,
    settings: Settings,
    *,
    actor_device_id: str | None,
    action: str,
    target: str,
    payload: object,
) -> AuditLogModel:
    _serialize_audit_writer(db)
    previous = db.scalar(select(AuditLogModel).order_by(AuditLogModel.audit_seq.desc()).limit(1))
    prev_hash = previous.entry_hash if previous is not None else _GENESIS_HASH
    event_id = uuid4().hex
    created_at = datetime.now(UTC)
    payload_hash = sha256_hex(payload)
    material = {
        "event_id": event_id,
        "actor_device_id": actor_device_id,
        "action": action,
        "target": target,
        "payload_hash": payload_hash,
        "prev_hash": prev_hash,
        "created_at": created_at.isoformat(),
    }
    entry_hash = hmac.new(_audit_key(settings), canonical_json(material), hashlib.sha256).hexdigest()
    entry = AuditLogModel(
        event_id=event_id,
        actor_device_id=actor_device_id,
        action=action,
        target=target,
        payload_hash=payload_hash,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
        created_at=created_at,
    )
    db.add(entry)
    db.flush()
    return entry


def verify_audit_chain(db: Session, settings: Settings) -> bool:
    previous_hash = _GENESIS_HASH
    entries = db.scalars(select(AuditLogModel).order_by(AuditLogModel.audit_seq.asc())).all()
    for entry in entries:
        if entry.prev_hash != previous_hash:
            return False
        material: dict[str, Any] = {
            "event_id": entry.event_id,
            "actor_device_id": entry.actor_device_id,
            "action": entry.action,
            "target": entry.target,
            "payload_hash": entry.payload_hash,
            "prev_hash": entry.prev_hash,
            "created_at": _as_utc(entry.created_at).isoformat(),
        }
        expected = hmac.new(_audit_key(settings), canonical_json(material), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, entry.entry_hash):
            return False
        previous_hash = entry.entry_hash
    return True



def _serialize_audit_writer(db: Session) -> None:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    # Fixed transaction-scoped advisory lock dedicated to the single canonical audit chain.
    # This prevents concurrent writers from observing the same previous hash and forking the chain.
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": 31051990544344148})

def _audit_key(settings: Settings) -> bytes:
    if settings.audit_hmac_key:
        return settings.audit_hmac_key.encode("utf-8")
    if settings.is_production:
        raise RuntimeError("production audit HMAC key is missing")
    return b"development-only-audit-key-never-use-in-production"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
