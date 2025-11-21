"""security.py
Core security and privacy helper functions:
- Password hashing (SHA-256 + per-user salt)
- Masking helpers for anonymization
- Optional Fernet encryption (reversible anonymization demonstration)

This module centralizes confidentiality / integrity related transformations.
"""

from __future__ import annotations
import os
import base64
import hashlib
import secrets
from typing import Tuple

try:
    from cryptography.fernet import Fernet
    _CRYPTO_AVAILABLE = True
except ImportError:  # cryptography optional
    _CRYPTO_AVAILABLE = False

FERNET_KEY_FILE = "fernet.key"


def generate_salt(length: int = 16) -> str:
    """Return a cryptographically secure random salt (hex)."""
    return secrets.token_hex(length)


def hash_password(plain: str, salt: str) -> str:
    """Hash password with SHA-256 + salt. (For assignment simplicity)"""
    h = hashlib.sha256()
    h.update(salt.encode("utf-8"))
    h.update(plain.encode("utf-8"))
    return h.hexdigest()


def verify_password(plain: str, salt: str, stored_hash: str) -> bool:
    """Verify plain password against stored salted hash."""
    return hash_password(plain, salt) == stored_hash


def mask_name(name: str) -> str:
    """Return masked name pattern ANON_XXXX (random hex suffix)."""
    return f"ANON_{secrets.token_hex(2).upper()}"  # 4 hex chars


def mask_contact(contact: str) -> str:
    """Return masked contact showing only last 3 digits (e.g. XXXXXXX789).

    Non-digit characters are ignored for masking purposes; result is a compact
    masked string composed of X's and the last three digits. If there are
    three or fewer digits the original digits are returned.
    """
    if not contact:
        return contact
    # extract digits only
    digits = "".join(ch for ch in contact if ch.isdigit())
    if not digits:
        return contact
    if len(digits) <= 3:
        return digits
    return "X" * (len(digits) - 3) + digits[-3:]


def load_or_create_fernet_key() -> bytes | None:
    """Load existing Fernet key or create a new one.

    Returns None if cryptography not available.
    Priority: ENV var FERNET_KEY -> key file -> generate new.
    """
    if not _CRYPTO_AVAILABLE:
        return None
    env_key = os.getenv("FERNET_KEY")
    if env_key:
        return env_key.encode("utf-8")
    if os.path.exists(FERNET_KEY_FILE):
        with open(FERNET_KEY_FILE, "rb") as f:
            return f.read().strip()
    key = Fernet.generate_key()
    with open(FERNET_KEY_FILE, "wb") as f:
        f.write(key)
    return key


def get_fernet() -> Fernet | None:
    """Return a Fernet instance if cryptography available; else None."""
    key = load_or_create_fernet_key()
    if key and _CRYPTO_AVAILABLE:
        return Fernet(key)
    return None


def encrypt_value(value: str, f: Fernet | None) -> str:
    """Encrypt value with Fernet if available; else return placeholder masked value."""
    if not value:
        return value
    if f is None:
        return value  # No encryption fallback
    token = f.encrypt(value.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_value(token: str, f: Fernet | None) -> str:
    """Decrypt Fernet token if possible; else return original token."""
    if f is None:
        return token
    try:
        return f.decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return token  # Graceful failure preserves availability


def anonymize_fields(name: str, contact: str, use_encryption: bool = False) -> Tuple[str, str]:
    """Return anonymized (masked or encrypted) versions of name & contact.

    If use_encryption=True and cryptography is available, ciphertext returned.
    Otherwise masking patterns returned.
    """
    if use_encryption and _CRYPTO_AVAILABLE:
        f = get_fernet()
        return encrypt_value(name, f), encrypt_value(contact, f)
    # Masking fallback
    return mask_name(name), mask_contact(contact)


def is_encrypted(value: str) -> bool:
    """Check if a value appears to be a Fernet encrypted token.
    
    Fernet tokens are base64-encoded and typically start with 'gAAAAA' prefix.
    Returns True if the value looks like an encrypted token, False otherwise.
    """
    if not value or not isinstance(value, str):
        return False
    # Fernet tokens are typically long base64 strings starting with 'gAAAAA'
    # and contain characters typical of base64 encoding
    if len(value) > 50 and value.startswith('gAAAAA'):
        return True
    return False
