from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Any


@dataclass
class RedisCacheAdapter:
    """Tenant-scoped read cache.

    This adapter is deliberately unsuitable as a financial source of truth. Every key is
    namespaced by an explicit platform/school scope and every write has a bounded TTL.
    """

    url: str
    scope: str
    _client: Any = field(default=None, init=False, repr=False)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.scope = self.scope.strip()
        if not self.scope:
            raise ValueError("Un scope de cache explicite est obligatoire")
        if any(ch.isspace() for ch in self.scope):
            raise ValueError("Scope de cache invalide")

    @property
    def client(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    import redis
                    self._client = redis.Redis.from_url(self.url, decode_responses=True)
        return self._client

    def _key(self, key: str) -> str:
        value = (key or "").strip()
        if not value:
            raise ValueError("Clé de cache obligatoire")
        return f"edusync:{self.scope}:{value}"

    def get(self, key: str) -> str | None:
        return self.client.get(self._key(key))

    def set(self, key: str, value: str, ttl_seconds: int = 300) -> None:
        if ttl_seconds < 1 or ttl_seconds > 3600:
            raise ValueError("TTL cache autorisé: 1..3600 secondes")
        self.client.set(self._key(key), value, ex=ttl_seconds)

    def delete(self, key: str) -> None:
        self.client.delete(self._key(key))
