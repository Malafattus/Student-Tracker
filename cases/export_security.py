import os
import shutil
import subprocess

from django.conf import settings


class SecureExportError(Exception):
    pass


def secure_export_binary():
    configured = getattr(settings, "SECURE_EXPORT_OPENSSL_BINARY", "openssl")
    resolved = shutil.which(configured)
    return resolved or configured


def secure_export_ready():
    binary = secure_export_binary()
    return bool(shutil.which(binary) or os.path.isabs(binary))


def _run_openssl(args, payload, passphrase):
    binary = secure_export_binary()
    if not secure_export_ready():
        raise SecureExportError("Secure export encryption is not available on this server yet.")

    env = os.environ.copy()
    env["SECURE_EXPORT_PASSPHRASE"] = passphrase
    process = subprocess.run(
        [
            binary,
            "enc",
            *args,
            "-pbkdf2",
            "-salt",
            "-iter",
            str(getattr(settings, "SECURE_EXPORT_PBKDF2_ITERATIONS", 200000)),
            "-pass",
            "env:SECURE_EXPORT_PASSPHRASE",
        ],
        input=payload,
        capture_output=True,
        env=env,
        check=False,
    )
    if process.returncode != 0:
        raise SecureExportError((process.stderr or b"").decode("utf-8", errors="ignore").strip() or "Secure export processing failed.")
    return process.stdout


def encrypt_export_bytes(payload, passphrase):
    return _run_openssl(["-aes-256-cbc"], payload, passphrase)


def decrypt_export_bytes(payload, passphrase):
    return _run_openssl(["-d", "-aes-256-cbc"], payload, passphrase)
