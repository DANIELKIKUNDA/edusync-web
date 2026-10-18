"""Profile photos (lot UX 2026-10): validated by content, re-encoded server-side, stored privately.

The uploaded bytes are never stored as such: the image is decoded (PNG, JPEG or WebP identified by its bytes,
never by the declared type), oriented, centre-cropped to a square, resized to 256 px and re-encoded as WebP.
Re-encoding strips every metadata block (EXIF, GPS position, camera serial) and any payload hidden in the file.
"""
from __future__ import annotations

import hashlib
from io import BytesIO
from uuid import UUID

AVATAR_MAX_UPLOAD = 5 * 1024 * 1024
AVATAR_SIDE = 256
AVATAR_MIN_SIDE = 64
AVATAR_MAX_SIDE = 8000


def process_avatar(data: bytes) -> tuple[bytes, str]:
    """(webp_bytes, sha256). Raises ValueError with a message for the user."""
    if not data:
        raise ValueError("Fichier vide.")
    if len(data) > AVATAR_MAX_UPLOAD:
        raise ValueError("La photo dépasse 5 Mo.")
    if not (data.startswith(b"\x89PNG\r\n\x1a\n") or data.startswith(b"\xff\xd8\xff") or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")):
        raise ValueError("Format refusé : choisissez une photo JPEG, PNG ou WebP.")
    from PIL import Image, ImageOps
    Image.MAX_IMAGE_PIXELS = 40_000_000          # refuse decompression bombs
    try:
        with Image.open(BytesIO(data)) as probe:
            probe.verify()
        with Image.open(BytesIO(data)) as img:
            w, h = img.size
            if min(w, h) < AVATAR_MIN_SIDE or max(w, h) > AVATAR_MAX_SIDE:
                raise ValueError(f"Dimensions refusées : au moins {AVATAR_MIN_SIDE} pixels de côté.")
            img = ImageOps.exif_transpose(img)
            img = ImageOps.fit(img.convert("RGB"), (AVATAR_SIDE, AVATAR_SIDE), method=Image.Resampling.LANCZOS, centering=(0.5, 0.42))
            out = BytesIO()
            img.save(out, format="WEBP", quality=86, method=6)
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 — corrupt, truncated or disguised file
        raise ValueError("Image illisible ou corrompue.") from exc
    webp = out.getvalue()
    return webp, hashlib.sha256(webp).hexdigest()


def avatar_key(user_id: UUID | str, sha256: str) -> str:
    return f"users/{user_id}/avatar-{sha256[:24]}.webp"
