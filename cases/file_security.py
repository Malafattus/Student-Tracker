import hashlib
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError


DEFAULT_ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
}

EICAR_SIGNATURE = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
SCRIPT_MARKERS = (b"<script", b"javascript:", b"vbscript:")


def allowed_upload_extensions():
    configured = getattr(settings, "ALLOWED_UPLOAD_EXTENSIONS", None)
    if configured:
        return {item.lower() for item in configured}
    return DEFAULT_ALLOWED_UPLOAD_EXTENSIONS


def max_upload_size_bytes():
    return int(getattr(settings, "MAX_UPLOAD_FILE_SIZE_BYTES", 10 * 1024 * 1024))


def suspicious_upload_reasons(uploaded_file):
    reasons = []
    extension = Path(uploaded_file.name or "").suffix.lower()
    if extension not in allowed_upload_extensions():
        reasons.append("This file type is not allowed.")

    if getattr(uploaded_file, "size", 0) > max_upload_size_bytes():
        reasons.append("This file is larger than the allowed upload limit.")

    position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else 0
    uploaded_file.seek(0)
    sample = uploaded_file.read(8192)
    uploaded_file.seek(position)

    lowered = sample.lower()
    if EICAR_SIGNATURE in sample:
        reasons.append("This file matches a malware test signature.")
    if extension in {".html", ".svg", ".js"} and any(marker in lowered for marker in SCRIPT_MARKERS):
        reasons.append("This file contains active script content.")
    if sample.startswith(b"MZ"):
        reasons.append("Executable files are not allowed.")
    return reasons


def file_sha256(uploaded_file):
    digest = hashlib.sha256()
    position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else 0
    uploaded_file.seek(0)
    for chunk in uploaded_file.chunks() if hasattr(uploaded_file, "chunks") else iter(lambda: uploaded_file.read(65536), b""):
        digest.update(chunk)
    uploaded_file.seek(position)
    return digest.hexdigest()


def file_size_bytes(uploaded_file):
    if hasattr(uploaded_file, "size") and uploaded_file.size is not None:
        return int(uploaded_file.size)
    position = uploaded_file.tell() if hasattr(uploaded_file, "tell") else 0
    uploaded_file.seek(0, 2)
    size = uploaded_file.tell()
    uploaded_file.seek(position)
    return size


def file_integrity_matches(uploaded_file, expected_sha256="", expected_size=0):
    if not uploaded_file or not expected_sha256:
        return False
    return file_sha256(uploaded_file) == expected_sha256 and file_size_bytes(uploaded_file) == int(expected_size or 0)


def validate_uploaded_file(uploaded_file):
    reasons = suspicious_upload_reasons(uploaded_file)
    if reasons:
        raise ValidationError(" ".join(reasons))
