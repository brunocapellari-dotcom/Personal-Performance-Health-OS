from __future__ import annotations

from datetime import UTC, datetime, timedelta

from healthos.config import Settings
from healthos.db import Database
from healthos.observation_pipeline import load_health_connect_records
from healthos.sync import IncomingChange, push_changes


def _settings() -> Settings:
    return Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        jwt_secret="j" * 40,
        audit_hmac_key="a" * 40,
    )


def _payload(source_record_id: str, observed: datetime, modified: datetime, kilograms: float) -> dict[str, object]:
    return {
        "record_type": "weight",
        "source_record_id": source_record_id,
        "observed_at_epoch_ms": int(observed.timestamp() * 1000),
        "data_origin_package": "com.synthetic.scale",
        "last_modified_at_epoch_ms": int(modified.timestamp() * 1000),
        "client_record_version": 1,
        "recording_method": 2,
        "health_connect_deleted": False,
        "data": {"kilograms": kilograms, "time": observed.isoformat()},
    }


def test_recreated_record_after_tombstone_becomes_visible_again() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)
    observed = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
    deleted = observed + timedelta(hours=1)
    recreated = deleted + timedelta(hours=1)

    with database.session() as db:
        push_changes(
            db,
            settings,
            device_id="synthetic-device",
            changes=(
                IncomingChange(
                    "record-old-0001",
                    "observation",
                    "record-old",
                    1,
                    False,
                    _payload("weight-record", observed, observed, 100.0),
                ),
                IncomingChange(
                    "record-delete-01",
                    "health_connect_tombstone",
                    "record-delete",
                    2,
                    False,
                    {
                        "record_type": "weight",
                        "source_record_id": "weight-record",
                        "observed_at_epoch_ms": int(deleted.timestamp() * 1000),
                        "data_origin_package": "health-connect",
                        "last_modified_at_epoch_ms": int(deleted.timestamp() * 1000),
                        "client_record_version": 0,
                        "recording_method": 0,
                        "health_connect_deleted": True,
                        "data": {},
                    },
                ),
                IncomingChange(
                    "record-new-0001",
                    "observation",
                    "record-new",
                    3,
                    False,
                    _payload("weight-record", observed, recreated, 99.5),
                ),
            ),
        )

    with database.session() as db:
        records = load_health_connect_records(db)

    assert len(records) == 1
    assert records[0][0] == "record-new"
    assert records[0][1].data["kilograms"] == 99.5


def test_latest_tombstone_hides_all_older_versions() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)
    observed = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
    modified = observed + timedelta(minutes=30)
    deleted = observed + timedelta(hours=1)

    with database.session() as db:
        push_changes(
            db,
            settings,
            device_id="synthetic-device",
            changes=(
                IncomingChange(
                    "record-old-0002",
                    "observation",
                    "record-old-a",
                    1,
                    False,
                    _payload("weight-record", observed, observed, 100.0),
                ),
                IncomingChange(
                    "record-old-0003",
                    "observation",
                    "record-old-b",
                    2,
                    False,
                    _payload("weight-record", observed, modified, 99.8),
                ),
                IncomingChange(
                    "record-delete-02",
                    "health_connect_tombstone",
                    "record-delete-b",
                    3,
                    False,
                    {
                        "record_type": "weight",
                        "source_record_id": "weight-record",
                        "observed_at_epoch_ms": int(deleted.timestamp() * 1000),
                        "data_origin_package": "health-connect",
                        "last_modified_at_epoch_ms": int(deleted.timestamp() * 1000),
                        "client_record_version": 0,
                        "recording_method": 0,
                        "health_connect_deleted": True,
                        "data": {},
                    },
                ),
            ),
        )

    with database.session() as db:
        records = load_health_connect_records(db)

    assert records == ()
