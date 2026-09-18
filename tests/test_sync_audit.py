from __future__ import annotations

from sqlalchemy import select

from healthos.audit import verify_audit_chain
from healthos.config import Settings
from healthos.db import Database
from healthos.models import AuditLogModel
from healthos.sync import IncomingChange, pull_changes, push_changes


def _settings() -> Settings:
    return Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="j" * 40,
        audit_hmac_key="a" * 40,
    )


def test_sync_is_idempotent_and_deterministic() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)
    first = IncomingChange("change-0001", "goal", "goal-1", 1, False, {"target": 10})
    stale = IncomingChange("change-0002", "goal", "goal-1", 1, False, {"target": 11})
    newer = IncomingChange("change-0003", "goal", "goal-1", 2, False, {"target": 12})

    with database.session() as db:
        result = push_changes(db, settings, device_id="phone-b", changes=(first,))
        assert result.accepted == ("change-0001",)
        duplicate = push_changes(db, settings, device_id="phone-b", changes=(first,))
        assert duplicate.duplicates == ("change-0001",)
        conflict = push_changes(db, settings, device_id="phone-a", changes=(stale,))
        assert conflict.conflicts == ("change-0002",)
        accepted = push_changes(db, settings, device_id="phone-a", changes=(newer,))
        assert accepted.accepted == ("change-0003",)
        pulled = pull_changes(db, after_cursor=0)
        assert [item.change_id for item in pulled] == ["change-0001", "change-0003"]
        assert verify_audit_chain(db, settings)


def test_append_only_health_history_cannot_be_overwritten() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)
    original = IncomingChange("obs-change-1", "observation", "obs-1", 1, False, {"weight": 100})
    altered = IncomingChange("obs-change-2", "observation", "obs-1", 2, False, {"weight": 90})
    with database.session() as db:
        assert push_changes(db, settings, device_id="phone", changes=(original,)).accepted
        assert push_changes(db, settings, device_id="phone", changes=(altered,)).conflicts == ("obs-change-2",)


def test_audit_chain_detects_tampering() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)
    with database.session() as db:
        push_changes(
            db,
            settings,
            device_id="phone",
            changes=(IncomingChange("change-1", "goal", "g", 1, False, {"target": 1}),),
        )
        assert verify_audit_chain(db, settings)
        first = db.scalar(select(AuditLogModel).order_by(AuditLogModel.audit_seq.asc()).limit(1))
        assert first is not None
        first.entry_hash = "f" * 64
        db.flush()
        assert not verify_audit_chain(db, settings)
