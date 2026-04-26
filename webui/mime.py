"""MIME type detection from file magic bytes."""
from __future__ import annotations

from pathlib import Path

MIME_SIGNATURES: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"RIFF", "image/webp"),
    (b"\x1a\x45\xdf\xa3", "video/webm"),
]


def detect_mime(filepath: Path) -> str:
    try:
        with open(filepath, "rb") as f:
            header = f.read(12)
    except OSError:
        return "application/octet-stream"

    for sig, mime in MIME_SIGNATURES:
        if header.startswith(sig):
            if sig == b"RIFF" and len(header) >= 12 and header[8:12] == b"WEBP":
                return "image/webp"
            elif sig == b"RIFF":
                continue
            return mime

    if len(header) >= 8 and header[4:8] == b"ftyp":
        return "video/mp4"

    return "application/octet-stream"
