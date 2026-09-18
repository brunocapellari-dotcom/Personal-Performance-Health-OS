from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .audit import append_audit
from .auth import sha256_hex
from .config import Settings
from .entity_payloads import validate_entity_payload
from .models import ChangeLogModel, EntityRecordModel

APPEND_ONLY_TYPES = frozenset(
    {
        "observation",
        "health_connect_tombstone",
        "performed_session",
        "checkin",
        "medication_event",
        "supplement_event",
        "assessment_result",
        "body_measurement",
    }
)


@dataclass(frozen=True)
class IncomingChange:
    change_id: str
    entity_type: str
    entity_id: str
    logical_clock: int
    deleted: bool
    payload: dict[str, Any]


@dataclass(frozen=True)
class PushResult:
    accepted: tuple[str, ...]
    duplicates: tuple[str, ...]
    conflicts: tuple[str, ...]
    cursor: int


@dataclass(frozen=True)
class PulledChange:
    server_seq: int
    change_id: str
    entity_type: str
    entity_id: str
    logical_clock: int
    origin_device_id: str
    deleted: bool
    payload: dict[str, Any]
    created_at: datetime


def push_changes(
    db: Session,
    settings: Settings,
    *,
    device_id: str,
    changes: tuple[IncomingChange, ...],
) -> PushResult:
    accepted: list[str] = []
    duplicates: list[str] = []
    conflicts: list[str] = []

    for change in changes:
        if change.logical_clock < 1:
            raise ValueError("logical_clock must be >= 1")
        if change.entity_type in APPEND_ONLY_TYPES and change.deleted:
            raise ValueError(f"{change.entity_type} is append-only and cannot be deleted")
        normalized_payload = validate_entity_payload(change.entity_type, change.entity_id, change.payload)
        if db.scalar(select(ChangeLogModel.change_id).where(ChangeLogModel.change_id == change.change_id)):
            duplicates.append(change.change_id)
            continue

        current = db.get(EntityRecordModel, (change.entity_type, change.entity_id))
        if current is not None and change.entity_type in APPEND_ONLY_TYPES:
            incoming_hash = sha256_hex(normalized_payload)
            current_hash = sha256_hex(current.payload)
            if incoming_hash != current_hash or current.deleted != change.deleted:
                conflicts.append(change.change_id)
                continue
            duplicates.append(change.change_id)
            continue

        incoming_order = (change.logical_clock, device_id)
        if current is not None and incoming_order <= (current.logical_clock, current.origin_device_id):
            conflicts.append(change.change_id)
            continue

        now = datetime.now(UTC)
        if current is None:
            current = EntityRecordModel(
                entity_type=change.entity_type,
                entity_id=change.entity_id,
                logical_clock=change.logical_clock,
                origin_device_id=device_id,
                deleted=change.deleted,
                payload=normalized_payload,
                updated_at=now,
            )
            db.add(current)
        else:
            current.logical_clock = change.logical_clock
            current.origin_device_id = device_id
            current.deleted = change.deleted
            current.payload = normalized_payload
            current.updated_at = now

        db.add(
            ChangeLogModel(
                change_id=change.change_id,
                entity_type=change.entity_type,
                entity_id=change.entity_id,
                logical_clock=change.logical_clock,
                origin_device_id=device_id,
                deleted=change.deleted,
                payload=normalized_payload,
                created_at=now,
            )
        )
        accepted.append(change.change_id)

    db.flush()
    cursor = int(db.scalar(select(func.coalesce(func.max(ChangeLogModel.server_seq), 0))) or 0)
    append_audit(
        db,
        settings,
        actor_device_id=device_id,
        action="sync.push",
        target="change_log",
        payload={
            "accepted": accepted,
            "duplicates": duplicates,
            "conflicts": conflicts,
            "cursor": cursor,
        },
    )
    return PushResult(tuple(accepted), tuple(duplicates), tuple(conflicts), cursor)


def pull_changes(db: Session, *, after_cursor: int, limit: int = 500) -> tuple[PulledChange, ...]:
    if after_cursor < 0:
        raise ValueError("after_cursor must be >= 0")
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    rows = db.scalars(
        select(ChangeLogModel)
        .where(ChangeLogModel.server_seq > after_cursor)
        .order_by(ChangeLogModel.server_seq.asc())
        .limit(limit)
    ).all()
    return tuple(
        PulledChange(
            server_seq=row.server_seq,
            change_id=row.change_id,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            logical_clock=row.logical_clock,
            origin_device_id=row.origin_device_id,
            deleted=row.deleted,
            payload=dict(row.payload),
            created_at=_as_utc(row.created_at),
        )
        for row in rows
    )


def current_cursor(db: Session) -> int:
    return int(db.scalar(select(func.coalesce(func.max(ChangeLogModel.server_seq), 0))) or 0)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
