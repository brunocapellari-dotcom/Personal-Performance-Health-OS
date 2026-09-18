from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import delete

from healthos.audit import append_audit, verify_audit_chain
from healthos.config import Settings
from healthos.db import Database
from healthos.models import AuditLogModel


@pytest.mark.postgres
def test_postgres_audit_chain_remains_linear_under_concurrent_writers() -> None:
    url = os.environ.get("HEALTHOS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("HEALTHOS_TEST_POSTGRES_URL is required for PostgreSQL concurrency test")

    settings = Settings(
        environment="test",
        database_url=url,
        jwt_secret="j" * 40,
        audit_hmac_key="a" * 40,
    )
    database = Database(settings)
    database.create_schema_for_tests(settings)

    with database.session() as db:
        db.execute(delete(AuditLogModel))

    def writer(index: int) -> None:
        with database.session() as db:
            append_audit(
                db,
                settings,
                actor_device_id=f"synthetic-device-{index}",
                action="concurrency.test",
                target=f"event-{index}",
                payload={"synthetic": True, "index": index},
            )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(writer, range(24)))

    with database.session() as db:
        assert verify_audit_chain(db, settings)
