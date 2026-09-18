from __future__ import annotations

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


@pytest.mark.postgres
def test_postgres_migrations_upgrade_downgrade_upgrade() -> None:
    url = os.environ.get("HEALTHOS_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("HEALTHOS_TEST_POSTGRES_URL is required for canonical PostgreSQL migration test")

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(config, "head")

    engine = create_engine(url)
    inspector = inspect(engine)
    expected = {"devices", "auth_challenges", "entity_records", "change_log", "audit_log", "plan_snapshots"}
    assert expected.issubset(set(inspector.get_table_names()))
    engine.dispose()

    command.downgrade(config, "base")
    engine = create_engine(url)
    inspector = inspect(engine)
    assert expected.isdisjoint(set(inspector.get_table_names()))
    engine.dispose()

    command.upgrade(config, "head")
