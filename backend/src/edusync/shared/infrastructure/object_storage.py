"""Object storage behind a provider-neutral port.

PostgreSQL keeps metadata and evidence; the object store keeps bytes. The S3 adapter speaks the plain
S3 REST protocol with AWS Signature V4 (no vendor SDK), so the same code targets SeaweedFS (local),
AWS S3, Cloudflare R2, Backblaze B2 or any S3-compatible service by configuration only:
EDUSYNC_OBJECT_STORAGE_ENDPOINT / _ACCESS_KEY / _SECRET_KEY / _BUCKET / _REGION.

Buckets stay private: nothing here creates a public policy or a permanent public URL. Browsers receive
short-lived signed links only (see documents.application.object_links).
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlsplit

import httpx

_UNSIGNED = "UNSIGNED-PAYLOAD"


class ObjectStorageError(RuntimeError):
    """Storage unavailable or refused the operation. Callers map it to a user-facing 503, never a 500 trace."""


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    sha256: str
    byte_size: int
    content_type: str


class ObjectStoragePort(Protocol):
    def ensure_bucket(self) -> None: ...
    def put(self, key: str, data: bytes, *, content_type: str, metadata: dict[str, str] | None = None) -> StoredObject: ...
    def get(self, key: str) -> bytes: ...
    def exists(self, key: str) -> bool: ...
    def delete(self, key: str) -> None: ...


def _validate_key(key: str) -> str:
    # Keys are built server-side from ids; refuse anything that could escape the tenant prefix.
    if not key or key.startswith("/") or "\\" in key or any(p in ("", ".", "..") for p in key.split("/")):
        raise ValueError("Clé d'objet invalide")
    return key


class LocalObjectStorage:
    """Development/test adapter on the local disk (same contract as S3)."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        target = self.root.joinpath(*_validate_key(key).split("/")).resolve()
        if self.root.resolve() not in target.parents:
            raise ValueError("Clé d'objet invalide")
        return target

    def ensure_bucket(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, data: bytes, *, content_type: str, metadata: dict[str, str] | None = None) -> StoredObject:
        target = self._path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)
        return StoredObject(key, hashlib.sha256(data).hexdigest(), len(data), content_type)

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise ObjectStorageError("Objet introuvable") from exc

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


class S3CompatibleObjectStorage:
    """Minimal S3 client (path-style addressing by default, which every S3-compatible server accepts)."""

    def __init__(self, *, endpoint: str, access_key: str, secret_key: str, bucket: str, region: str = "us-east-1",
                 path_style: bool = True, timeout_seconds: float = 20.0, transport: httpx.BaseTransport | None = None):
        if not endpoint or not access_key or not secret_key or not bucket:
            raise ValueError("Stockage objet incomplet : endpoint, clés et bucket sont obligatoires")
        parts = urlsplit(endpoint.rstrip("/"))
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("EDUSYNC_OBJECT_STORAGE_ENDPOINT doit être une URL http(s)")
        self.scheme, self.netloc, self.base_path = parts.scheme, parts.netloc, parts.path
        self.access_key, self.secret_key, self.bucket, self.region = access_key, secret_key, bucket, region
        self.path_style = path_style
        self.client = httpx.Client(timeout=timeout_seconds, transport=transport)

    # -- request building -------------------------------------------------------------------------
    def _host_and_path(self, key: str | None) -> tuple[str, str]:
        obj = "" if key is None else "/" + quote(_validate_key(key), safe="/-_.~")
        if self.path_style:
            return self.netloc, f"{self.base_path}/{quote(self.bucket, safe='')}{obj}"
        return f"{self.bucket}.{self.netloc}", f"{self.base_path}{obj or '/'}"

    def _signing_key(self, day: str) -> bytes:
        k = _sign(("AWS4" + self.secret_key).encode("utf-8"), day)
        return _sign(_sign(_sign(k, self.region), "s3"), "aws4_request")

    def _signature(self, method: str, path: str, query: dict[str, str], headers: dict[str, str], payload_hash: str, amz_date: str) -> tuple[str, str]:
        canonical_query = "&".join(f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in sorted(query.items()))
        names = sorted(h.lower() for h in headers)
        lowered = {k.lower(): " ".join(str(v).strip().split()) for k, v in headers.items()}
        canonical_headers = "".join(f"{n}:{lowered[n]}\n" for n in names)
        signed = ";".join(names)
        canonical = "\n".join([method, path, canonical_query, canonical_headers, signed, payload_hash])
        scope = f"{amz_date[:8]}/{self.region}/s3/aws4_request"
        to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode("utf-8")).hexdigest()])
        return signed, hmac.new(self._signing_key(amz_date[:8]), to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    def _request(self, method: str, key: str | None, *, body: bytes = b"", extra_headers: dict[str, str] | None = None,
                 query: dict[str, str] | None = None, now: datetime | None = None) -> httpx.Response:
        host, path = self._host_and_path(key)
        amz_date = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        payload_hash = hashlib.sha256(body).hexdigest()
        headers = {"host": host, "x-amz-date": amz_date, "x-amz-content-sha256": payload_hash, **(extra_headers or {})}
        signed, signature = self._signature(method, path, query or {}, headers, payload_hash, amz_date)
        headers["Authorization"] = (f"AWS4-HMAC-SHA256 Credential={self.access_key}/{amz_date[:8]}/{self.region}/s3/aws4_request, "
                                    f"SignedHeaders={signed}, Signature={signature}")
        url = f"{self.scheme}://{host}{path}"
        try:
            return self.client.request(method, url, params=query or None, content=body or None, headers=headers)
        except httpx.HTTPError as exc:
            raise ObjectStorageError("Stockage des documents injoignable") from exc

    # -- port -----------------------------------------------------------------------------------
    def ensure_bucket(self) -> None:
        r = self._request("HEAD", None)
        if r.status_code == 200:
            return
        if r.status_code == 404:
            created = self._request("PUT", None)
            if created.status_code in (200, 409):
                return
            raise ObjectStorageError(f"Création du bucket refusée (HTTP {created.status_code})")
        raise ObjectStorageError(f"Bucket inaccessible (HTTP {r.status_code})")

    def put(self, key: str, data: bytes, *, content_type: str, metadata: dict[str, str] | None = None) -> StoredObject:
        headers = {"content-type": content_type}
        for k, v in (metadata or {}).items():
            # Metadata travels as ASCII HTTP headers; non-ASCII values are percent-encoded.
            headers[f"x-amz-meta-{k.lower()}"] = quote(str(v), safe=" -_.~:@/")
        r = self._request("PUT", key, body=data, extra_headers=headers)
        if r.status_code not in (200, 201):
            raise ObjectStorageError(f"Écriture refusée par le stockage (HTTP {r.status_code})")
        return StoredObject(key, hashlib.sha256(data).hexdigest(), len(data), content_type)

    def get(self, key: str) -> bytes:
        r = self._request("GET", key)
        if r.status_code == 200:
            return r.content
        if r.status_code == 404:
            raise ObjectStorageError("Objet introuvable")
        raise ObjectStorageError(f"Lecture refusée par le stockage (HTTP {r.status_code})")

    def exists(self, key: str) -> bool:
        r = self._request("HEAD", key)
        if r.status_code in (200, 404):
            return r.status_code == 200
        raise ObjectStorageError(f"Stockage indisponible (HTTP {r.status_code})")

    def delete(self, key: str) -> None:
        r = self._request("DELETE", key)
        if r.status_code not in (200, 204, 404):
            raise ObjectStorageError(f"Suppression refusée par le stockage (HTTP {r.status_code})")

    def presign_get(self, key: str, *, expires_seconds: int = 300, now: datetime | None = None,
                    response_content_type: str | None = None, response_content_disposition: str | None = None) -> str:
        """Short-lived signed GET (max 1 h). Only useful when the storage endpoint is reachable by the browser."""
        if not 1 <= expires_seconds <= 3600:
            raise ValueError("Durée de lien signé hors limites (1 s à 1 h)")
        host, path = self._host_and_path(key)
        amz_date = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
        query = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{self.access_key}/{amz_date[:8]}/{self.region}/s3/aws4_request",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(expires_seconds),
            "X-Amz-SignedHeaders": "host",
        }
        if response_content_type:
            query["response-content-type"] = response_content_type
        if response_content_disposition:
            query["response-content-disposition"] = response_content_disposition
        _, signature = self._signature("GET", path, query, {"host": host}, _UNSIGNED, amz_date)
        query["X-Amz-Signature"] = signature
        qs = "&".join(f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in sorted(query.items()))
        return f"{self.scheme}://{host}{path}?{qs}"


def build_object_storage(settings) -> ObjectStoragePort | None:
    """None when no storage is configured: document features then answer 503 with a clear message."""
    backend = (settings.object_storage_backend or "").lower()
    if backend == "local":
        return LocalObjectStorage(Path(settings.object_storage_local_root))
    if backend == "s3" or (backend in ("", "auto") and settings.object_storage_endpoint):
        return S3CompatibleObjectStorage(
            endpoint=settings.object_storage_endpoint, access_key=settings.object_storage_access_key,
            secret_key=settings.object_storage_secret_key, bucket=settings.object_storage_bucket,
            region=settings.object_storage_region or "us-east-1", path_style=settings.object_storage_path_style,
        )
    return None
