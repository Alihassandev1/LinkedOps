from datetime import datetime, timedelta, timezone
from typing import Optional, Any

import bcrypt
from jose import JWTError, jwt
from cryptography.fernet import Fernet

from app.core.config import settings

# ── Password hashing (direct bcrypt — no passlib) ─────────────────────────────
# passlib is unmaintained and runs an internal self-test on first use that
# breaks against bcrypt >= 4.0 (ValueError: password cannot be longer than
# 72 bytes). Calling bcrypt directly avoids that self-test entirely and is
# simpler besides — passlib was only ever a thin wrapper around this.

_BCRYPT_MAX_BYTES = 72  # bcrypt's hard algorithm limit — not a passlib quirk


def hash_password(password: str) -> str:
    """Hash a plain-text password. Truncates to 72 bytes (bcrypt's own limit)."""
    password_bytes = password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a stored bcrypt hash."""
    password_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.checkpw(password_bytes, hashed_password.encode("utf-8"))


# ───────────────────── JWT tokens ────────────────────────────────────────────
def create_access_token(subject: Any, expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived JWT access token."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": str(subject), "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(subject: Any) -> str:
    """Create a long-lived JWT refresh token."""
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {"sub": str(subject), "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT.
    Raises JWTError if invalid or expired.
    """
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])


# ───────── Fernet symmetric encryption (for LinkedIn OAuth tokens) ──────────
# LinkedIn access tokens must NEVER be stored in plain text.
_fernet = Fernet(settings.FERNET_KEY.encode())


def encrypt_token(plain_token: str) -> str:
    """Encrypt a LinkedIn OAuth token before storing in DB."""
    return _fernet.encrypt(plain_token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a stored LinkedIn OAuth token for use in API calls."""
    return _fernet.decrypt(encrypted_token.encode()).decode()