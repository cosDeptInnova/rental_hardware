from .redis_control import allow_rate_limit


class RedisSlidingWindowRateLimiter:
    def allow(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        return allow_rate_limit(key=key, limit=limit, window_seconds=window_seconds)


rate_limiter = RedisSlidingWindowRateLimiter()
