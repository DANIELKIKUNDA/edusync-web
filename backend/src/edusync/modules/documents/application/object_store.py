"""Documents on object storage: school logo, generated-document archive, short-lived signed links.

Tenant isolation is layered: object keys are built server-side under schools/<school_id>/, PostgreSQL
metadata is under FORCE RLS, every read re-checks that the key belongs to the caller's school, and the
bucket is private (browsers only ever receive a signed link valid a few minutes).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import re
import time
import unicodedata
from io import BytesIO
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from edusync.shared.infrastructure.object_storage import ObjectStorageError, ObjectStoragePort

log = logging.getLogger("edusync.documents")
LOGO_MAX_BYTES = 1_048_576
LOGO_MIN_SIDE, LOGO_MAX_SIDE = 32, 4096
FORMATS = {"PDF": "application/pdf", "XLSX": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "CSV": "text/csv"}

_storage: ObjectStoragePort | None = None


def configure_storage(storage: ObjectStoragePort | None) -> None:
    """Called once by the application factory; document generators read the logo through it."""
    global _storage
    _storage = storage


def storage_available() -> bool:
    return _storage is not None


# --- names ---------------------------------------------------------------------------------------
def safe_file_name(name: str, *, max_len: int = 120) -> str:
    """ASCII, no path separators or control characters; keeps a readable name for downloads."""
    value = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9._ -]+", "_", value).strip(" ._") or "document"
    stem, dot, ext = value.rpartition(".")
    if dot and 1 <= len(ext) <= 5:
        return stem[: max_len - len(ext) - 1].strip(" ._") + "." + ext.lower()
    return value[:max_len]


# --- logo ----------------------------------------------------------------------------------------
def validate_logo(data: bytes) -> tuple[str, str]:
    """Content is identified by its bytes, never by the declared type or file name."""
    if not data:
        raise ValueError("Fichier vide.")
    if len(data) > LOGO_MAX_BYTES:
        raise ValueError("Le logo dépasse 1 Mo.")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        content_type, ext = "image/png", "png"
    elif data.startswith(b"\xff\xd8\xff"):
        content_type, ext = "image/jpeg", "jpg"
    else:
        raise ValueError("Format refusé : seuls les logos PNG ou JPEG sont acceptés.")
    from PIL import Image
    try:
        with Image.open(BytesIO(data)) as img:
            img.verify()
        with Image.open(BytesIO(data)) as img:
            w, h = img.size
    except Exception as exc:  # noqa: BLE001 — any decoding error means a corrupt or disguised file
        raise ValueError("Image illisible ou corrompue.") from exc
    if min(w, h) < LOGO_MIN_SIDE or max(w, h) > LOGO_MAX_SIDE:
        raise ValueError(f"Dimensions refusées : entre {LOGO_MIN_SIDE} et {LOGO_MAX_SIDE} pixels.")
    return content_type, ext


def logo_key(school_id: UUID | str, sha256: str, ext: str) -> str:
    return f"schools/{school_id}/branding/logo-{sha256[:24]}.{ext}"


def logo_stream(school: dict[str, Any]) -> BytesIO | None:
    """Logo for PDF/XLSX generators. Never reads a server file path; only this school's stored object."""
    key, school_id = school.get("logo_object_key"), school.get("id")
    if not key or not school_id or _storage is None or not str(key).startswith(f"schools/{school_id}/branding/"):
        return None
    try:
        return BytesIO(_storage.get(str(key)))
    except (ObjectStorageError, ValueError):
        log.warning("school logo unavailable for documents", extra={"school_id": str(school_id)})
        return None


# --- generated documents archive ----------------------------------------------------------------
def archive_generated(conn, actor, *, data: bytes, fmt: str, document_code: str, title: str, file_name: str, required_capability: str,
                      academic_year_id: UUID | str | None = None, filters: dict[str, Any] | None = None) -> str | None:
    """Best effort: the user always receives the document; archiving failure is logged, never blocking."""
    if _storage is None or fmt not in FORMATS:
        return None
    gen_id = uuid4()
    name = safe_file_name(file_name)
    logical = f"schools/{actor.school_id}/documents/{safe_file_name(document_code)}/{name}"
    key = f"schools/{actor.school_id}/documents/{safe_file_name(document_code)}/{gen_id}-{name}"
    try:
        stored = _storage.put(key, data, content_type=FORMATS[fmt], metadata={"school-id": str(actor.school_id), "generation-id": str(gen_id), "document-code": document_code})
    except (ObjectStorageError, ValueError):
        log.warning("document archive skipped: storage unavailable", extra={"document_code": document_code})
        return None
    params = {"id": str(gen_id), "sid": str(actor.school_id), "y": str(academic_year_id) if academic_year_id else None, "code": document_code,
              "fmt": fmt, "title": title[:240], "key": key, "logical": logical, "sha": stored.sha256, "size": stored.byte_size,
              "uid": str(actor.user_id), "ct": FORMATS[fmt], "fn": name, "cap": required_capability, "filters": json.dumps(filters or {}, default=str)}
    try:
        # Savepoint: an archive failure never aborts the business transaction that produced the document.
        with conn.begin_nested():
            conn.execute(text("""INSERT INTO generated_documents(id,school_id,academic_year_id,document_code,format,title,object_key,logical_key,sha256,byte_size,
                filters_json,generated_by,content_type,file_name,required_capability) VALUES(:id,:sid,:y,:code,:fmt,:title,:key,:logical,:sha,:size,CAST(:filters AS jsonb),:uid,:ct,:fn,:cap)"""), params)
            conn.execute(text("""INSERT INTO current_documents(school_id,logical_key,latest_generation_id,document_code,format,title,object_key,sha256,byte_size,academic_year_id,updated_by,updated_at)
                VALUES(:sid,:logical,:id,:code,:fmt,:title,:key,:sha,:size,:y,:uid,now())
                ON CONFLICT(school_id,logical_key) DO UPDATE SET latest_generation_id=EXCLUDED.latest_generation_id,title=EXCLUDED.title,object_key=EXCLUDED.object_key,
                  sha256=EXCLUDED.sha256,byte_size=EXCLUDED.byte_size,updated_by=EXCLUDED.updated_by,updated_at=now()"""), params)
    except Exception:  # noqa: BLE001
        log.exception("document archive metadata not recorded", extra={"document_code": document_code})
        return None
    return str(gen_id)


def archive_official_pdf_strict(conn, actor, *, data: bytes, document_code: str, title: str, file_name: str,
                                required_capability: str) -> tuple[str, str]:
    """Store and index an official PDF or raise; callers roll back its numbered report on any failure.

    The object key is returned so a failed outer DB commit can remove its orphan object.
    """
    if _storage is None:
        raise ObjectStorageError("Archivage officiel indisponible")
    gen_id = uuid4()
    name = safe_file_name(file_name)
    logical = f"schools/{actor.school_id}/documents/{safe_file_name(document_code)}/{name}"
    key = f"schools/{actor.school_id}/documents/{safe_file_name(document_code)}/{gen_id}-{name}"
    stored = _storage.put(key, data, content_type=FORMATS["PDF"],
                          metadata={"school-id": str(actor.school_id), "generation-id": str(gen_id), "document-code": document_code})
    params = {"id": str(gen_id), "sid": str(actor.school_id), "code": document_code,
              "title": title[:240], "key": key, "logical": logical, "sha": stored.sha256,
              "size": stored.byte_size, "uid": str(actor.user_id), "ct": FORMATS["PDF"],
              "fn": name, "cap": required_capability}
    try:
        conn.execute(text("""INSERT INTO generated_documents(id,school_id,document_code,format,title,object_key,logical_key,sha256,byte_size,
            filters_json,generated_by,content_type,file_name,required_capability)
            VALUES(:id,:sid,:code,'PDF',:title,:key,:logical,:sha,:size,'{}'::jsonb,:uid,:ct,:fn,:cap)"""), params)
        conn.execute(text("""INSERT INTO current_documents(school_id,logical_key,latest_generation_id,document_code,format,title,object_key,sha256,byte_size,updated_by,updated_at)
            VALUES(:sid,:logical,:id,:code,'PDF',:title,:key,:sha,:size,:uid,now())
            ON CONFLICT(school_id,logical_key) DO UPDATE SET latest_generation_id=EXCLUDED.latest_generation_id,title=EXCLUDED.title,
              object_key=EXCLUDED.object_key,sha256=EXCLUDED.sha256,byte_size=EXCLUDED.byte_size,updated_by=EXCLUDED.updated_by,updated_at=now()"""), params)
    except Exception:
        try:
            _storage.delete(key)
        except Exception:
            log.exception("official PDF orphan cleanup failed")
        raise
    return str(gen_id), key


def read_official_pdf(key: str, school_id: UUID | str) -> bytes:
    if _storage is None or not key.startswith(f"schools/{school_id}/documents/"):
        raise ObjectStorageError("Rapport officiel archivé indisponible")
    return _storage.get(key)


def discard_official_pdf(key: str) -> None:
    if _storage is not None:
        try:
            _storage.delete(key)
        except Exception:
            log.exception("official PDF orphan cleanup failed")


def archive_generated_tx(services, actor, **kwargs) -> str | None:
    """Same as archive_generated, for routes that build the document after their read transaction."""
    if _storage is None:
        return None
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
            return archive_generated(conn, actor, **kwargs)
    except Exception:  # noqa: BLE001 — archiving never blocks the download
        log.exception("document archive transaction failed")
        return None


def school_wide_capabilities(actor) -> list[str]:
    """Only explicit SCHOOL grants authorize reading school-wide archives."""
    out = []
    for cap in actor.permissions:
        scopes = actor.scopes_for(cap)
        if any(t == "SCHOOL" for t, _ in scopes):
            out.append(cap)
    return sorted(out)


# --- signed links ----------------------------------------------------------------------------------
def _link_key(settings) -> bytes:
    secret = settings.document_link_secret or ("edusync-document-links:" + settings.jwt_secret)
    return hashlib.sha256(secret.encode("utf-8")).digest()


def sign_link(settings, *, document_id: str, school_id: str, user_id: str, now: float | None = None) -> tuple[str, int]:
    exp = int((now or time.time()) + settings.document_link_seconds)
    payload = f"{document_id}.{school_id}.{user_id}.{exp}"
    mac = hmac.new(_link_key(settings), payload.encode(), hashlib.sha256).digest()
    token = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=") + "." + base64.urlsafe_b64encode(mac).decode().rstrip("=")
    return token, exp


def verify_link(settings, token: str, *, now: float | None = None) -> dict[str, str]:
    try:
        body, mac = token.split(".", 1)
        payload = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode()
        given = base64.urlsafe_b64decode(mac + "=" * (-len(mac) % 4))
        document_id, school_id, user_id, exp = payload.split(".")
    except Exception as exc:  # noqa: BLE001
        raise PermissionError("Lien invalide") from exc
    expected = hmac.new(_link_key(settings), payload.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(given, expected):
        raise PermissionError("Lien invalide")
    if int(exp) < int(now or time.time()):
        raise PermissionError("Lien expiré")
    return {"document_id": document_id, "school_id": school_id, "user_id": user_id}
