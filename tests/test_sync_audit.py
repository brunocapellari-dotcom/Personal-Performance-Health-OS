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


def _goal_payload(goal_id: str, target: float) -> dict[str, object]:
    return {
        "goal_id": goal_id,
        "description": "Synthetic goal",
        "priority": 3,
        "baseline": 5.0,
        "current": 6.0,
        "target": target,
        "metric": "synthetic_metric",
        "constraints": [],
    }


def test_sync_is_idempotent_and_deterministic() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)
    first = IncomingChange("change-0001", "goal", "goal-1", 1, False, _goal_payload("goal-1", 10))
    stale = IncomingChange("change-0002", "goal", "goal-1", 1, False, _goal_payload("goal-1", 11))
    newer = IncomingChange("change-0003", "goal", "goal-1", 2, False, _goal_payload("goal-1", 12))

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
    original = IncomingChange(
        "obs-change-1",
        "observation",
        "obs-1",
        1,
        False,
        {"metric": "weight", "value": 100.0, "unit": "kg"},
    )
    altered = IncomingChange(
        "obs-change-2",
        "observation",
        "obs-1",
        2,
        False,
        {"metric": "weight", "value": 90.0, "unit": "kg"},
    )
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
            changes=(IncomingChange("change-1", "goal", "g", 1, False, _goal_payload("g", 1)),),
        )
        assert verify_audit_chain(db, settings)
        first = db.scalar(select(AuditLogModel).order_by(AuditLogModel.audit_seq.asc()).limit(1))
        assert first is not None
        first.entry_hash = "f" * 64
        db.flush()
        assert not verify_audit_chain(db, settings)


def test_sync_rejects_unknown_or_malformed_entity_payloads() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)
    with database.session() as db:
        import pytest

        with pytest.raises(ValueError, match="unsupported entity_type"):
            push_changes(
                db,
                settings,
                device_id="phone",
                changes=(IncomingChange("bad-change-1", "mystery", "x", 1, False, {"x": 1}),),
            )
        with pytest.raises(ValueError, match="entity_id must match"):
            push_changes(
                db,
                settings,
                device_id="phone",
                changes=(
                    IncomingChange(
                        "bad-change-2",
                        "goal",
                        "goal-a",
                        1,
                        False,
                        _goal_payload("goal-b", 10),
                    ),
                ),
            )
