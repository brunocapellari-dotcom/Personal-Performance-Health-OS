from __future__ import annotations

import base64
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    database_url: str = "sqlite+pysqlite:///:memory:"
    bootstrap_token: str | None = None
    jwt_secret: str | None = None
    audit_hmac_key: str | None = None
    blob_encryption_key_b64: str | None = None
    backup_encryption_key_b64: str | None = None
    blob_directory: str = ".healthos-blobs"
    access_token_minutes: int = 15
    challenge_ttl_seconds: int = 300
    test_bearer_token: str | None = None
    fdc_api_key: str | None = None
    open_food_facts_user_agent: str = "PersonalPerformanceHealthOS/0.2"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            environment=os.getenv("HEALTHOS_ENV", "development").strip().lower(),
            database_url=os.getenv("HEALTHOS_DATABASE_URL", "sqlite+pysqlite:///:memory:").strip(),
            bootstrap_token=os.getenv("HEALTHOS_BOOTSTRAP_TOKEN") or None,
            jwt_secret=os.getenv("HEALTHOS_JWT_SECRET") or None,
            audit_hmac_key=os.getenv("HEALTHOS_AUDIT_HMAC_KEY") or None,
            blob_encryption_key_b64=os.getenv("HEALTHOS_BLOB_KEY_B64") or None,
            backup_encryption_key_b64=os.getenv("HEALTHOS_BACKUP_KEY_B64") or None,
            blob_directory=os.getenv("HEALTHOS_BLOB_DIRECTORY", ".healthos-blobs").strip(),
            access_token_minutes=int(os.getenv("HEALTHOS_ACCESS_TOKEN_MINUTES", "15")),
            challenge_ttl_seconds=int(os.getenv("HEALTHOS_CHALLENGE_TTL_SECONDS", "300")),
            test_bearer_token=os.getenv("HEALTHOS_TEST_BEARER_TOKEN") or None,
            fdc_api_key=os.getenv("HEALTHOS_FDC_API_KEY") or None,
            open_food_facts_user_agent=os.getenv(
                "HEALTHOS_OPEN_FOOD_FACTS_USER_AGENT",
                "PersonalPerformanceHealthOS/0.2",
            ).strip(),
        )

    @property
    def is_production(self) -> bool:
        return self.environment in {"production", "prod"}

    def blob_key(self) -> bytes | None:
        return self._decode_key(self.blob_encryption_key_b64, "HEALTHOS_BLOB_KEY_B64")

    def backup_key(self) -> bytes | None:
        return self._decode_key(self.backup_encryption_key_b64, "HEALTHOS_BACKUP_KEY_B64")

    def _decode_key(self, encoded: str | None, name: str) -> bytes | None:
        if encoded is None:
            return None
        try:
            value = base64.urlsafe_b64decode(encoded.encode("ascii"))
        except Exception as exc:  # pragma: no cover - exact decoder error is implementation-specific
            raise RuntimeError(f"{name} must be valid URL-safe base64") from exc
        if len(value) != 32:
            raise RuntimeError(f"{name} must decode to exactly 32 bytes")
        return value

    def validate(self) -> None:
        if self.access_token_minutes <= 0 or self.access_token_minutes > 60:
            raise RuntimeError("HEALTHOS_ACCESS_TOKEN_MINUTES must be between 1 and 60")
        if self.challenge_ttl_seconds < 30 or self.challenge_ttl_seconds > 900:
            raise RuntimeError("HEALTHOS_CHALLENGE_TTL_SECONDS must be between 30 and 900")
        if self.test_bearer_token and self.is_production:
            raise RuntimeError("HEALTHOS_TEST_BEARER_TOKEN is forbidden in production")
        if not self.open_food_facts_user_agent:
            raise RuntimeError("HEALTHOS_OPEN_FOOD_FACTS_USER_AGENT cannot be empty")
        if self.blob_encryption_key_b64 is not None:
            self.blob_key()
        if self.backup_encryption_key_b64 is not None:
            self.backup_key()
        if not self.is_production:
            return
        if not self.database_url.startswith(("postgresql+psycopg://", "postgresql://")):
            raise RuntimeError("production database URL must use PostgreSQL")
        for name, value in (
            ("HEALTHOS_BOOTSTRAP_TOKEN", self.bootstrap_token),
            ("HEALTHOS_JWT_SECRET", self.jwt_secret),
            ("HEALTHOS_AUDIT_HMAC_KEY", self.audit_hmac_key),
        ):
            if not value or len(value) < 32:
                raise RuntimeError(f"production requires {name} with at least 32 characters")
        if self.blob_key() is None:
            raise RuntimeError("production requires HEALTHOS_BLOB_KEY_B64 for encrypted blob storage")
        if self.backup_key() is None:
            raise RuntimeError("production requires HEALTHOS_BACKUP_KEY_B64 for encrypted backups")
        if self.backup_key() == self.blob_key():
            raise RuntimeError("production backup and blob encryption keys must be different")
