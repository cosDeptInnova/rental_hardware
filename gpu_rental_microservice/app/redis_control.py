import time
from redis import Redis

from .config import settings


_redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


RATE_LIMIT_LUA = """
local zkey = KEYS[1]
local now = tonumber(ARGV[1])
local window_start = now - tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', zkey, '-inf', window_start)
local current = redis.call('ZCARD', zkey)
if current >= limit then
  return 0
end
redis.call('ZADD', zkey, now, tostring(now) .. '-' .. tostring(math.random(1000000)))
redis.call('EXPIRE', zkey, tonumber(ARGV[2]) + 2)
return 1
"""

ACQUIRE_SLOT_LUA = """
local counter_key = KEYS[1]
local token_key = KEYS[2]
local max_slots = tonumber(ARGV[1])
local lease_seconds = tonumber(ARGV[2])
local current = tonumber(redis.call('GET', counter_key) or '0')
if current >= max_slots then
  return 0
end
redis.call('INCR', counter_key)
redis.call('SET', token_key, '1', 'EX', lease_seconds)
redis.call('EXPIRE', counter_key, lease_seconds)
return 1
"""

RELEASE_SLOT_LUA = """
local counter_key = KEYS[1]
local token_key = KEYS[2]
if redis.call('DEL', token_key) == 1 then
  local current = tonumber(redis.call('GET', counter_key) or '0')
  if current > 0 then
    redis.call('DECR', counter_key)
  end
end
return 1
"""


def redis_client() -> Redis:
    return _redis_client


def allow_rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    now = time.time()
    allowed = _redis_client.eval(RATE_LIMIT_LUA, 1, f"rl:{key}", now, window_seconds, limit)
    return bool(int(allowed))


def acquire_global_slot(client_name: str, job_id: str, max_slots: int, lease_seconds: int) -> bool:
    counter_key = f"conc:{client_name}:count"
    token_key = f"conc:{client_name}:job:{job_id}"
    result = _redis_client.eval(ACQUIRE_SLOT_LUA, 2, counter_key, token_key, max_slots, lease_seconds)
    return bool(int(result))


def refresh_global_slot(client_name: str, job_id: str, lease_seconds: int):
    _redis_client.expire(f"conc:{client_name}:job:{job_id}", lease_seconds)
    _redis_client.expire(f"conc:{client_name}:count", lease_seconds)


def release_global_slot(client_name: str, job_id: str):
    _redis_client.eval(RELEASE_SLOT_LUA, 2, f"conc:{client_name}:count", f"conc:{client_name}:job:{job_id}")


RELEASE_LOCK_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


def acquire_client_submission_lock(client_name: str, token: str, ttl_seconds: int) -> bool:
    return bool(_redis_client.set(f"submit-lock:{client_name}", token, nx=True, ex=ttl_seconds))


def release_client_submission_lock(client_name: str, token: str):
    _redis_client.eval(RELEASE_LOCK_LUA, 1, f"submit-lock:{client_name}", token)
