from __future__ import annotations

import base64

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from healthos.auth import (
    authenticate_active_token,
    authenticate_token,
    create_challenge,
    enroll_device,
    issue_access_token,
    require_owner,
    verify_challenge,
)
from healthos.blob_store import EncryptedBlobStore
from healthos.config import Settings
from healthos.db import Database


def _settings() -> Settings:
    return Settings(
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
        bootstrap_token="b" * 40,
        jwt_secret="j" * 40,
        audit_hmac_key="a" * 40,
        blob_encryption_key_b64=base64.urlsafe_b64encode(b"k" * 32).decode("ascii"),
    )


def test_device_challenge_is_signed_bound_and_single_use() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    with database.session() as db:
        enroll_device(db, device_id="phone-1", public_key_pem=public_pem)
        challenge = create_challenge(db, device_id="phone-1", settings=settings)
        signature = private_key.sign(challenge.nonce.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
        token = verify_challenge(
            db,
            challenge_id=challenge.challenge_id,
            signature_b64=base64.b64encode(signature).decode("ascii"),
            settings=settings,
        )
        principal = authenticate_token(token, settings)
        assert principal.device_id == "phone-1"
        require_owner(principal)
        with pytest.raises(ValueError, match="expired or already used"):
            verify_challenge(
                db,
                challenge_id=challenge.challenge_id,
                signature_b64=base64.b64encode(signature).decode("ascii"),
                settings=settings,
            )


def test_disabled_device_invalidates_existing_token_immediately() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    with database.session() as db:
        device = enroll_device(db, device_id="revoked-1", public_key_pem=public_pem)
        token = issue_access_token(device=device, settings=settings)
        assert authenticate_active_token(db, token, settings).device_id == "revoked-1"
        device.enabled = False
        db.flush()
        with pytest.raises(ValueError, match="disabled or no longer enrolled"):
            authenticate_active_token(db, token, settings)



def test_readonly_principal_cannot_mutate() -> None:
    settings = _settings()
    database = Database(settings)
    database.create_schema_for_tests(settings)
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    with database.session() as db:
        device = enroll_device(db, device_id="readonly-1", public_key_pem=public_pem, role="readonly")
        principal = authenticate_token(issue_access_token(device=device, settings=settings), settings)
        with pytest.raises(PermissionError):
            require_owner(principal)


def test_encrypted_blob_store_roundtrip_and_tamper_detection(tmp_path) -> None:
    store = EncryptedBlobStore(tmp_path, b"z" * 32)
    ref = store.put(b"private-health-photo", media_type="image/jpeg")
    encrypted = next(tmp_path.rglob("*.blob")).read_bytes()
    assert b"private-health-photo" not in encrypted
    assert store.get(ref.blob_id, media_type="image/jpeg") == b"private-health-photo"
    with pytest.raises(InvalidTag):
        store.get(ref.blob_id, media_type="image/png")
