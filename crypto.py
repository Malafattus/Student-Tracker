import base64
import hashlib
import hmac
import os

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


LEGACY_PREFIX = "enc1$"
VERSIONED_PREFIX = "enc2$"
NONCE_LENGTH = 16
TAG_LENGTH = 32
LEGACY_KEY_ID = "legacy"


def field_encryption_ready():
    return bool(_keyring())


def field_encryption_uses_dedicated_key():
    return bool(getattr(settings, "FIELD_ENCRYPTION_DEDICATED_KEY_CONFIGURED", False))


def field_encryption_rotation_ready():
    return len(_keyring()) > 1


def active_field_key_id():
    return _active_key_id()


def encrypted_text_version(value):
    if not isinstance(value, str):
        return None
    if value.startswith(VERSIONED_PREFIX):
        parts = value.split("$", 2)
        if len(parts) == 3:
            return parts[1]
    if value.startswith(LEGACY_PREFIX):
        return LEGACY_KEY_ID
    return None


def is_encrypted_text(value):
    return encrypted_text_version(value) is not None


def encrypt_text(value, *, force_reencrypt=False):
    if value in (None, ""):
        return value
    if is_encrypted_text(value) and not force_reencrypt:
        return value
    plaintext = decrypt_text(value) if is_encrypted_text(value) else str(value)
    nonce = os.urandom(NONCE_LENGTH)
    key_id = _active_key_id()
    ciphertext = _xor_bytes(plaintext.encode("utf-8"), _keystream(len(plaintext.encode("utf-8")), nonce, key_id))
    tag = hmac.new(_derive_key(b"field-mac", key_id), nonce + ciphertext, hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(nonce + ciphertext + tag).decode("ascii")
    return f"{VERSIONED_PREFIX}{key_id}${token}"


def decrypt_text(value):
    if value in (None, ""):
        return value
    if isinstance(value, str) and value.startswith(VERSIONED_PREFIX):
        _, version, token = value.split("$", 2)
        raw = base64.urlsafe_b64decode(token.encode("ascii"))
        nonce = raw[:NONCE_LENGTH]
        tag = raw[-TAG_LENGTH:]
        ciphertext = raw[NONCE_LENGTH:-TAG_LENGTH]
        expected_tag = hmac.new(_derive_key(b"field-mac", version), nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            raise ValueError("Encrypted text failed integrity verification.")
        plaintext = _xor_bytes(ciphertext, _keystream(len(ciphertext), nonce, version))
        return plaintext.decode("utf-8")
    if isinstance(value, str) and value.startswith(LEGACY_PREFIX):
        raw = base64.urlsafe_b64decode(value[len(LEGACY_PREFIX) :].encode("ascii"))
        nonce = raw[:NONCE_LENGTH]
        tag = raw[-TAG_LENGTH:]
        ciphertext = raw[NONCE_LENGTH:-TAG_LENGTH]
        expected_tag = hmac.new(_derive_key(b"field-mac", LEGACY_KEY_ID), nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected_tag):
            raise ValueError("Encrypted text failed integrity verification.")
        plaintext = _xor_bytes(ciphertext, _keystream(len(ciphertext), nonce, LEGACY_KEY_ID))
        return plaintext.decode("utf-8")
    return value


def needs_reencryption(value):
    version = encrypted_text_version(value)
    if version is None:
        return bool(value)
    return version != _active_key_id()


def _keyring():
    configured = getattr(settings, "FIELD_ENCRYPTION_KEYS", {})
    if configured:
        return {str(key_id): str(secret).encode("utf-8") for key_id, secret in configured.items() if secret}
    fallback = getattr(settings, "FIELD_ENCRYPTION_KEY", "")
    if fallback:
        return {LEGACY_KEY_ID: fallback.encode("utf-8")}
    return {}


def _active_key_id():
    keyring = _keyring()
    configured = getattr(settings, "FIELD_ENCRYPTION_ACTIVE_KEY", "") or ""
    if configured:
        if configured not in keyring:
            raise ImproperlyConfigured(f"FIELD_ENCRYPTION_ACTIVE_KEY '{configured}' is not present in FIELD_ENCRYPTION_KEYS.")
        return configured
    if LEGACY_KEY_ID in keyring and len(keyring) == 1:
        return LEGACY_KEY_ID
    if keyring:
        return next(iter(keyring))
    raise ImproperlyConfigured("No field encryption key is configured.")


def _field_encryption_key(key_id):
    keyring = _keyring()
    if key_id not in keyring:
        raise ImproperlyConfigured(f"Field encryption key '{key_id}' is not configured.")
    return keyring[key_id]


def _derive_key(label, key_id):
    return hmac.new(_field_encryption_key(key_id), label, hashlib.sha256).digest()


def _xor_bytes(left, right):
    return bytes(a ^ b for a, b in zip(left, right))


def _keystream(length, nonce, key_id):
    key = _derive_key(b"field-encryption", key_id)
    blocks = bytearray()
    counter = 0
    while len(blocks) < length:
        counter_bytes = counter.to_bytes(4, "big")
        blocks.extend(hmac.new(key, nonce + counter_bytes, hashlib.sha256).digest())
        counter += 1
    return bytes(blocks[:length])
