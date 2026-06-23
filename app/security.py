"""Hashing de contraseñas (PBKDF2, stdlib) y tokens. Sin dependencias externas."""

from __future__ import annotations

import hashlib
import hmac
import secrets

_ITERATIONS = 240_000
_ALGO = "sha256"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(_ALGO, password.encode(), salt.encode(), _ITERATIONS)
    return f"pbkdf2_{_ALGO}${_ITERATIONS}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iters, salt, digest = stored.split("$")
        iterations = int(iters)
        algo = scheme.split("_", 1)[1]
    except (ValueError, IndexError):
        return False
    dk = hashlib.pbkdf2_hmac(algo, password.encode(), salt.encode(), iterations)
    return hmac.compare_digest(dk.hex(), digest)


def new_api_key() -> str:
    return "egl_" + secrets.token_urlsafe(32)
