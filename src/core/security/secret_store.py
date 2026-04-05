import ctypes
import base64
import json
import os
from ctypes import wintypes
from pathlib import Path
from typing import Optional

from core.pathing import data_path, is_frozen, resource_path


_SECRET_FILE = data_path(".secrets", "leetify_api.bin")
_DPAPI_ENTROPY = b"Internomat::LeetifyAPI::v1"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _blob_from_bytes(data: bytes) -> DATA_BLOB:
    if not data:
        return DATA_BLOB(0, None)
    buffer = (ctypes.c_byte * len(data)).from_buffer_copy(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))


def _bytes_from_blob(blob: DATA_BLOB) -> bytes:
    if blob.cbData == 0 or not blob.pbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def _crypt_protect(raw: bytes, entropy: bytes) -> bytes:
    in_blob = _blob_from_bytes(raw)
    entropy_blob = _blob_from_bytes(entropy)
    out_blob = DATA_BLOB()

    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    ok = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        flags,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError(f"CryptProtectData failed: {ctypes.GetLastError()}")

    try:
        return _bytes_from_blob(out_blob)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def _crypt_unprotect(protected: bytes, entropy: bytes) -> bytes:
    in_blob = _blob_from_bytes(protected)
    entropy_blob = _blob_from_bytes(entropy)
    out_blob = DATA_BLOB()

    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    ok = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        ctypes.byref(entropy_blob),
        None,
        None,
        flags,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError(f"CryptUnprotectData failed: {ctypes.GetLastError()}")

    try:
        return _bytes_from_blob(out_blob)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)


def secret_file_path() -> Path:
    return _SECRET_FILE


def save_leetify_api(api_key: str) -> Path:
    if os.name != "nt":
        raise RuntimeError("Encrypted local secret storage is only supported on Windows.")

    value = (api_key or "").strip()
    if not value:
        raise ValueError("LEETIFY API key cannot be empty.")

    encrypted = _crypt_protect(value.encode("utf-8"), _DPAPI_ENTROPY)
    _SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SECRET_FILE.write_bytes(encrypted)
    return _SECRET_FILE


def load_leetify_api() -> Optional[str]:
    if os.name != "nt" or not _SECRET_FILE.exists():
        return None

    try:
        decrypted = _crypt_unprotect(_SECRET_FILE.read_bytes(), _DPAPI_ENTROPY)
        value = decrypted.decode("utf-8").strip()
        return value or None
    except Exception:
        return None


def _xor_bytes(payload: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(payload))


def load_bootstrap_leetify_api() -> Optional[str]:
    """Load obfuscated build-time bootstrap key bundled for first-run DPAPI migration."""
    if not is_frozen():
        return None

    bundle_path = resource_path("bootstrap", "leetify_bootstrap.bin")
    if not bundle_path.exists():
        return None

    try:
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
        key = base64.b64decode(payload.get("k", ""))
        cipher = base64.b64decode(payload.get("p", ""))
        if not key or not cipher:
            return None
        value = _xor_bytes(cipher, key).decode("utf-8").strip()
        return value or None
    except Exception:
        return None
