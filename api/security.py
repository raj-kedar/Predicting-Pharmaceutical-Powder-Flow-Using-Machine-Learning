"""
Password hashing and signed bearer tokens, standard library only.

The scrypt format is unchanged, so existing accounts keep working. Tokens carry
a fingerprint of the password hash, so changing a password revokes old tokens.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import time
from functools import lru_cache

_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1
_SALT_BYTES = 16
_KEY_LEN = 32
_MAX_MEM = 64 * 1024 * 1024
MIN_PASSWORD = 8
MAX_PASSWORD = 256
_MAX_TOKEN_LENGTH = 2048


def hash_password(password: str) -> str:
    if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        raise ValueError(f"Password must be {MIN_PASSWORD} to {MAX_PASSWORD} characters.")
    salt = os.urandom(_SALT_BYTES)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R,
                         p=_SCRYPT_P, dklen=_KEY_LEN, maxmem=_MAX_MEM)
    return "scrypt${}${}${}${}${}".format(_SCRYPT_N, _SCRYPT_R, _SCRYPT_P,
                                          base64.b64encode(salt).decode(),
                                          base64.b64encode(key).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, key_b64 = stored.split("$")
        if scheme != "scrypt" or len(password) > MAX_PASSWORD:
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(key_b64, validate=True)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r),
                                p=int(p), dklen=len(expected), maxmem=_MAX_MEM)
    except (ValueError, TypeError, binascii.Error, UnicodeError):
        return False
    return hmac.compare_digest(actual, expected)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return hash_password(secrets.token_urlsafe(16))


def burn_password_check(password: str) -> None:
    """Spend the same time as a real check so response time cannot reveal valid emails."""
    verify_password(password, _dummy_hash())


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii") + b"=" * (-len(text) % 4), altchars=b"-_",
                            validate=True)


def _sign(secret: str, message: str) -> bytes:
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).digest()


def password_fingerprint(secret: str, password_hash: str) -> str:
    return _b64e(_sign(secret, f"pwv:{password_hash}"))[:22]


def create_token(secret: str, user_id: int, email: str, role: str, password_hash: str,
                 ttl_seconds: int) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": str(user_id), "email": email, "role": role, "iat": now,
               "exp": now + ttl_seconds, "jti": secrets.token_urlsafe(8),
               "pwv": password_fingerprint(secret, password_hash)}
    signing_input = "{}.{}".format(_b64e(json.dumps(header, separators=(",", ":")).encode()),
                                   _b64e(json.dumps(payload, separators=(",", ":")).encode()))
    return f"{signing_input}.{_b64e(_sign(secret, signing_input))}"


def decode_token(secret: str, token: str) -> dict | None:
    """Return the payload, or None for any malformed, forged or expired token."""
    if not token or len(token) > _MAX_TOKEN_LENGTH:
        return None
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
        signature = _b64d(signature_b64)
        if not hmac.compare_digest(signature, _sign(secret, f"{header_b64}.{payload_b64}")):
            return None
        header = json.loads(_b64d(header_b64))
        payload = json.loads(_b64d(payload_b64))
        if not isinstance(header, dict) or header.get("alg") != "HS256":
            return None
        if not isinstance(payload, dict) or int(payload["exp"]) <= int(time.time()):
            return None
        payload["sub"] = int(payload["sub"])
    except (ValueError, TypeError, KeyError, binascii.Error, UnicodeError):
        return None
    return payload


def generate_secret() -> str:
    return secrets.token_urlsafe(48)
