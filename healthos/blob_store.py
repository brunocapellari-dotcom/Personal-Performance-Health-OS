from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@dataclass(frozen=True)
class BlobRef:
    blob_id: str
    size_bytes: int
    sha256: str


class EncryptedBlobStore:
    """Encrypted reference blob store for photos and attachments.

    The ciphertext format is: 12-byte nonce || AES-GCM ciphertext+tag. The encryption
    key must come from a secret manager / Android Keystore boundary, never source control.
    """

    def __init__(self, root: str | Path, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("AES-256-GCM requires a 32-byte key")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._cipher = AESGCM(key)

    def put(self, data: bytes, *, media_type: str) -> BlobRef:
        digest = hashlib.sha256(data).hexdigest()
        blob_id = digest
        target = self._path(blob_id)
        if not target.exists():
            nonce = os.urandom(12)
            aad = media_type.encode("utf-8")
            ciphertext = self._cipher.encrypt(nonce, data, aad)
            target.write_bytes(nonce + ciphertext)
        return BlobRef(blob_id=blob_id, size_bytes=len(data), sha256=digest)

    def get(self, blob_id: str, *, media_type: str) -> bytes:
        raw = self._path(blob_id).read_bytes()
        if len(raw) < 13:
            raise ValueError("corrupt encrypted blob")
        nonce, ciphertext = raw[:12], raw[12:]
        return self._cipher.decrypt(nonce, ciphertext, media_type.encode("utf-8"))

    def delete(self, blob_id: str) -> bool:
        target = self._path(blob_id)
        if not target.exists():
            return False
        target.unlink()
        return True

    def _path(self, blob_id: str) -> Path:
        if len(blob_id) != 64 or any(ch not in "0123456789abcdef" for ch in blob_id):
            raise ValueError("invalid blob id")
        directory = self.root / blob_id[:2]
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{blob_id}.blob"
