import base64
import hashlib
import hmac
import io
import secrets
import struct
import time
from urllib.parse import quote

try:
    import segno
except ModuleNotFoundError:  # pragma: no cover - exercised only where optional dependency is unavailable
    segno = None


def generate_totp_secret(length=32):
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def normalize_totp_secret(secret):
    return "".join((secret or "").upper().split())


def format_totp_secret(secret):
    normalized = normalize_totp_secret(secret)
    return " ".join(normalized[index : index + 4] for index in range(0, len(normalized), 4))


def _hotp(secret, counter, digits=6):
    key = base64.b32decode(normalize_totp_secret(secret), casefold=True)
    message = struct.pack(">Q", counter)
    digest = hmac.new(key, message, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10**digits)).zfill(digits)


def current_totp_code(secret, at_time=None, step=30, digits=6):
    timestamp = at_time if at_time is not None else time.time()
    counter = int(timestamp // step)
    return _hotp(secret, counter, digits=digits)


def verify_totp_code(secret, code, at_time=None, step=30, digits=6, window=1):
    normalized_code = "".join((code or "").split())
    if not normalized_code.isdigit() or len(normalized_code) != digits:
        return False
    timestamp = at_time if at_time is not None else time.time()
    counter = int(timestamp // step)
    for offset in range(-window, window + 1):
        if _hotp(secret, counter + offset, digits=digits) == normalized_code:
            return True
    return False


def provisioning_uri(secret, username, issuer):
    normalized = normalize_totp_secret(secret)
    return f"otpauth://totp/{quote(issuer)}:{quote(username)}?secret={normalized}&issuer={quote(issuer)}"


def provisioning_qr_svg_data_uri(secret, username, issuer):
    if segno is None:
        return None
    uri = provisioning_uri(secret, username, issuer)
    qr = segno.make(uri)
    buffer = io.StringIO()
    qr.save(buffer, kind="svg", scale=5, border=2, dark="#0f2f57", light="#ffffff")
    svg_markup = buffer.getvalue()
    return f"data:image/svg+xml;utf8,{quote(svg_markup)}"
