from __future__ import annotations

import base64
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import delete

from healthos.audit import append_audit, verify_audit_chain
from healthos.auth import consume_pairing_token, create_challenge, create_pairing_token, enroll_device, verify_challenge
from healthos.config import Settings
from healthos.db import Database
from healthos.models import AuditLogModel, AuthChallengeModel, DeviceModel, PairingTokenModel


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



def _reset_auth_tables(database: Database) -> None:
    with database.session() as db:
        db.execute(delete(AuthChallengeModel))
        db.execute(delete(PairingTokenModel))
        db.execute(delete(DeviceModel))


@pytest.mark.postgres
def test_postgres_pairing_token_has_exactly_one_concurrent_winner() -> None:
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
    _reset_auth_tables(database)

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    with database.session() as db:
        enroll_device(db, device_id="pairing-race-owner", public_key_pem=public_pem)
        token, _ = create_pairing_token(
            db,
            issued_by_device_id="pairing-race-owner",
            role="readonly",
            ttl_seconds=300,
        )

    def consume(_: int) -> bool:
        try:
            with database.session() as db:
                consume_pairing_token(db, token=token, requested_role="readonly")
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(consume, range(8)))
    assert results.count(True) == 1
    assert results.count(False) == 7


@pytest.mark.postgres
def test_postgres_auth_challenge_has_exactly_one_concurrent_winner() -> None:
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
    _reset_auth_tables(database)

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    with database.session() as db:
        enroll_device(db, device_id="challenge-race-device", public_key_pem=public_pem)
        challenge = create_challenge(db, device_id="challenge-race-device", settings=settings)
        signature = private_key.sign(challenge.nonce.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        signature_b64 = base64.b64encode(signature).decode("ascii")
        challenge_id = challenge.challenge_id

    def verify(_: int) -> bool:
        try:
            with database.session() as db:
                verify_challenge(
                    db,
                    challenge_id=challenge_id,
                    signature_b64=signature_b64,
                    settings=settings,
                )
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(verify, range(8)))
    assert results.count(True) == 1
    assert results.count(False) == 7
