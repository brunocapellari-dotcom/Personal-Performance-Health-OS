from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import AuthChallengeModel, DeviceModel


@dataclass(frozen=True)
class Principal:
    device_id: str
    role: str


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def sha256_hex(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def secure_compare(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return False
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def enroll_device(db: Session, *, device_id: str, public_key_pem: str, role: str = "owner_device") -> DeviceModel:
    if role not in {"owner_device", "readonly"}:
        raise ValueError("unsupported role")
    existing = db.get(DeviceModel, device_id)
    if existing is not None:
        if existing.public_key_pem != public_key_pem or existing.role != role:
            raise ValueError("device identity already enrolled with different credentials")
        return existing
    _load_ec_public_key(public_key_pem)
    device = DeviceModel(device_id=device_id, public_key_pem=public_key_pem, role=role, enabled=True)
    db.add(device)
    db.flush()
    return device


def create_challenge(db: Session, *, device_id: str, settings: Settings) -> AuthChallengeModel:
    device = db.get(DeviceModel, device_id)
    if device is None or not device.enabled:
        raise ValueError("unknown or disabled device")
    challenge = AuthChallengeModel(
        challenge_id=uuid4().hex,
        device_id=device_id,
        nonce=secrets.token_urlsafe(48),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.challenge_ttl_seconds),
    )
    db.add(challenge)
    db.flush()
    return challenge


def verify_challenge(
    db: Session,
    *,
    challenge_id: str,
    signature_b64: str,
    settings: Settings,
) -> str:
    challenge = db.get(AuthChallengeModel, challenge_id)
    if challenge is None:
        raise ValueError("challenge not found")
    now = datetime.now(UTC)
    if challenge.used_at is not None or _as_utc(challenge.expires_at) < now:
        raise ValueError("challenge expired or already used")
    device = db.get(DeviceModel, challenge.device_id)
    if device is None or not device.enabled:
        raise ValueError("unknown or disabled device")
    signature = _decode_signature(signature_b64)
    public_key = _load_ec_public_key(device.public_key_pem)
    try:
        public_key.verify(signature, challenge.nonce.encode("utf-8"), ec.ECDSA(hashes.SHA256()))
    except InvalidSignature as exc:
        raise ValueError("invalid device signature") from exc
    challenge.used_at = now
    device.last_seen_at = now
    db.flush()
    return issue_access_token(device=device, settings=settings, now=now)


def issue_access_token(*, device: DeviceModel, settings: Settings, now: datetime | None = None) -> str:
    if not settings.jwt_secret:
        raise RuntimeError("HEALTHOS_JWT_SECRET is required to issue access tokens")
    issued = now or datetime.now(UTC)
    payload: dict[str, Any] = {
        "iss": "healthos",
        "aud": "healthos-api",
        "sub": device.device_id,
        "role": device.role,
        "iat": int(issued.timestamp()),
        "exp": int((issued + timedelta(minutes=settings.access_token_minutes)).timestamp()),
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def authenticate_token(token: str, settings: Settings) -> Principal:
    if settings.test_bearer_token and not settings.is_production and secure_compare(token, settings.test_bearer_token):
        return Principal(device_id="test-device", role="owner_device")
    if not settings.jwt_secret:
        raise ValueError("JWT verification is not configured")
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience="healthos-api",
            issuer="healthos",
            options={"require": ["exp", "iat", "sub", "role", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise ValueError("invalid access token") from exc
    device_id = str(payload["sub"])
    role = str(payload["role"])
    if role not in {"owner_device", "readonly"}:
        raise ValueError("invalid role claim")
    return Principal(device_id=device_id, role=role)


def authenticate_active_token(db: Session, token: str, settings: Settings) -> Principal:
    principal = authenticate_token(token, settings)
    if (
        settings.test_bearer_token
        and not settings.is_production
        and principal.device_id == "test-device"
        and secure_compare(token, settings.test_bearer_token)
    ):
        return principal
    device = active_device(db, principal.device_id)
    if device is None:
        raise ValueError("device is disabled or no longer enrolled")
    if device.role != principal.role:
        raise ValueError("device role changed; re-authentication required")
    return principal


def require_owner(principal: Principal) -> None:
    if principal.role != "owner_device":
        raise PermissionError("owner_device role required")


def active_device(db: Session, device_id: str) -> DeviceModel | None:
    return db.scalar(select(DeviceModel).where(DeviceModel.device_id == device_id, DeviceModel.enabled.is_(True)))


def public_key_fingerprint(public_key_pem: str) -> str:
    public_key = _load_ec_public_key(public_key_pem)
    der = public_key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def _load_ec_public_key(public_key_pem: str) -> ec.EllipticCurvePublicKey:
    try:
        key = serialization.load_pem_public_key(public_key_pem.encode("utf-8"))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid public key") from exc
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError("device key must be ECDSA P-256")
    return key


def _decode_signature(signature_b64: str) -> bytes:
    try:
        return base64.b64decode(signature_b64, validate=True)
    except ValueError as exc:
        raise ValueError("signature must be valid base64") from exc


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
