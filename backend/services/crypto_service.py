"""Envelope encryption for sensitive at-rest secrets.

Uses Fernet (AES-128-CBC + HMAC-SHA256) with a base64-encoded key from
`SECRETS_KEK`. Encrypted values are prefixed with `enc::v1::` so callers can
distinguish plaintext (legacy) from ciphertext during the transition period.

Rotation: append a new key to `SECRETS_KEK_OLD` (comma-separated) — decryption
tries the primary key first, then each old key. Re-encryption on read migrates
legacy plaintext + old-key ciphertext into fresh primary-key ciphertext.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

log = logging.getLogger("cpaas.crypto")

_ENC_PREFIX = "enc::v1::"

_primary: Optional[Fernet] = None
_multi: Optional[MultiFernet] = None


def _init() -> None:
    global _primary, _multi
    if _primary is not None:
        return
    kek = (os.environ.get("SECRETS_KEK") or "").strip()
    if not kek:
        log.warning("SECRETS_KEK is not set — secret encryption disabled. Set it in .env for production.")
        return
    try:
        _primary = Fernet(kek.encode())
    except Exception as e:
        log.error("SECRETS_KEK is not a valid Fernet key: %s", e)
        return
    keys = [_primary]
    old = (os.environ.get("SECRETS_KEK_OLD") or "").strip()
    if old:
        for k in old.split(","):
            k = k.strip()
            if not k:
                continue
            try:
                keys.append(Fernet(k.encode()))
            except Exception as e:
                log.warning("SECRETS_KEK_OLD contains invalid key, skipping: %s", e)
    _multi = MultiFernet(keys)


def is_encrypted(value: Optional[str]) -> bool:
    return bool(value) and isinstance(value, str) and value.startswith(_ENC_PREFIX)


def encrypt(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt a secret. Returns the original value unchanged when KEK is not
    configured (dev mode) or when the value is empty/already encrypted."""
    if not plaintext:
        return plaintext
    if is_encrypted(plaintext):
        return plaintext
    _init()
    if _primary is None:
        return plaintext  # dev fallback
    token = _primary.encrypt(plaintext.encode()).decode()
    return _ENC_PREFIX + token


def decrypt(value: Optional[str]) -> Optional[str]:
    """Decrypt a secret if it looks encrypted. Legacy plaintext values are
    returned as-is so migration is idempotent and non-breaking."""
    if not value:
        return value
    if not is_encrypted(value):
        return value  # legacy plaintext — return unchanged
    _init()
    if _multi is None:
        log.error("Cannot decrypt secret: SECRETS_KEK is not configured")
        return value
    try:
        return _multi.decrypt(value[len(_ENC_PREFIX):].encode()).decode()
    except InvalidToken:
        log.error("Failed to decrypt secret: token invalid (rotation may be needed)")
        return value


def encrypt_dict(doc: dict, fields: list) -> dict:
    """Encrypt specific fields on a dict in-place; returns the same dict."""
    if not doc:
        return doc
    for f in fields:
        v = doc.get(f)
        if isinstance(v, str) and v:
            doc[f] = encrypt(v)
    return doc


def decrypt_dict(doc: Optional[dict], fields: list) -> Optional[dict]:
    """Decrypt specific fields on a dict in-place; returns the same dict."""
    if not doc:
        return doc
    for f in fields:
        v = doc.get(f)
        if isinstance(v, str) and v:
            doc[f] = decrypt(v)
    return doc
