from __future__ import annotations

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings


class SessionControl:
    def __init__(self) -> None:
        self._client: Redis | None = None
        self._fallback_revoked: set[str] = set()

    def _client_or_none(self) -> Redis | None:
        if self._client is not None:
            return self._client
        try:
            client = Redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            self._client = client
            return client
        except RedisError:
            return None

    @staticmethod
    def _key(tenant_id: str) -> str:
        return f"gpu_broker:session_revoked:{tenant_id}"

    def revoke(self, tenant_id: str) -> None:
        client = self._client_or_none()
        if client is None:
            self._fallback_revoked.add(tenant_id)
            return
        client.set(self._key(tenant_id), "1")

    def restore(self, tenant_id: str) -> None:
        client = self._client_or_none()
        if client is None:
            self._fallback_revoked.discard(tenant_id)
            return
        client.delete(self._key(tenant_id))

    def is_revoked(self, tenant_id: str) -> bool:
        client = self._client_or_none()
        if client is None:
            return tenant_id in self._fallback_revoked
        return bool(client.exists(self._key(tenant_id)))


session_control = SessionControl()
