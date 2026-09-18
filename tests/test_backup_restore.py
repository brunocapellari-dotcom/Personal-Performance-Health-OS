from __future__ import annotations

import base64

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import func, select

from healthos.audit import append_audit, verify_audit_chain
from healthos.backup import export_backup, restore_backup
from healthos.config import Settings
from healthos.db import Database
from healthos.models import AuditLogModel, ChangeLogModel, DeviceModel, EntityRecordModel
from healthos.sync import IncomingChange, push_changes


def _settings(*, backup_key: bytes = b"r" * 32) -> Settings:
    return Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        bootstrap_token="b" * 40,
        jwt_secret="j" * 40,
        audit_hmac_key="a" * 40,
        blob_encryption_key_b64=base64.urlsafe_b64encode(b"k" * 32).decode("ascii"),
        backup_encryption_key_b64=base64.urlsafe_b64encode(backup_key).decode("ascii"),
    )


def test_backup_restore_roundtrip_preserves_state_and_audit_chain() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)

    with database.session() as db:
        db.add(DeviceModel(device_id="phone-1", public_key_pem="synthetic-test-key", role="owner_device"))
        db.flush()
        push_changes(
            db,
            settings,
            device_id="phone-1",
            changes=(
                IncomingChange(
                    change_id="change-1",
                    entity_type="goal",
                    entity_id="goal-strength",
                    logical_clock=1,
                    deleted=False,
                    payload={
                        "goal_id": "goal-strength",
                        "description": "synthetic strength goal",
                        "priority": 1,
                        "baseline": 1.0,
                        "current": 1.2,
                        "target": 2.0,
                        "metric": "strength",
                        "constraints": [],
                    },
                ),
            ),
        )
        append_audit(
            db,
            settings,
            actor_device_id="phone-1",
            action="backup.fixture",
            target="test",
            payload={"synthetic": True},
        )
        backup = export_backup(db, settings)
        assert backup.startswith(b"HOSB1")
        assert b"synthetic strength goal" not in backup
        expected_audits = int(db.scalar(select(func.count()).select_from(AuditLogModel)) or 0)
        expected_changes = int(db.scalar(select(func.count()).select_from(ChangeLogModel)) or 0)

    with database.session() as db:
        db.query(AuditLogModel).delete()
        db.query(ChangeLogModel).delete()
        db.query(EntityRecordModel).delete()
        db.query(DeviceModel).delete()

    with database.session() as db:
        restore_backup(db, settings, backup, destructive=True)
        assert db.get(DeviceModel, "phone-1") is not None
        goal = db.get(EntityRecordModel, ("goal", "goal-strength"))
        assert goal is not None
        assert goal.payload["description"] == "synthetic strength goal"
        assert int(db.scalar(select(func.count()).select_from(AuditLogModel)) or 0) == expected_audits
        assert int(db.scalar(select(func.count()).select_from(ChangeLogModel)) or 0) == expected_changes
        assert verify_audit_chain(db, settings)


def test_restore_requires_explicit_destructive_flag() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)
    with database.session() as db:
        backup = export_backup(db, settings)
        with pytest.raises(PermissionError, match="destructive=True"):
            restore_backup(db, settings, backup)


def test_backup_rejects_wrong_key_and_tampering() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)
    with database.session() as db:
        append_audit(
            db,
            settings,
            actor_device_id=None,
            action="backup.fixture",
            target="test",
            payload={"synthetic": True},
        )
        backup = export_backup(db, settings)

    wrong_settings = _settings(backup_key=b"w" * 32)
    with database.session() as db:
        with pytest.raises(InvalidTag):
            restore_backup(db, wrong_settings, backup, destructive=True)

    tampered = bytearray(backup)
    tampered[-1] ^= 0x01
    with database.session() as db:
        with pytest.raises(InvalidTag):
            restore_backup(db, settings, bytes(tampered), destructive=True)
