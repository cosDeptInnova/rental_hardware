import time

from .config import settings
from .redis_control import redis_client


def enqueue_job(job_id: str):
    redis_client().rpush(settings.redis_job_queue_key, job_id)


def schedule_retry(job_id: str, delay_seconds: int):
    score = time.time() + delay_seconds
    redis_client().zadd(settings.redis_delayed_queue_key, {job_id: score})


def promote_delayed_jobs(batch_size: int = 100):
    now = time.time()
    r = redis_client()
    due = r.zrangebyscore(settings.redis_delayed_queue_key, min='-inf', max=now, start=0, num=batch_size)
    if not due:
        return 0
    pipe = r.pipeline()
    for job_id in due:
        pipe.zrem(settings.redis_delayed_queue_key, job_id)
        pipe.rpush(settings.redis_job_queue_key, job_id)
    pipe.execute()
    return len(due)


def dequeue_job(timeout_seconds: int = 2) -> str | None:
    item = redis_client().blpop(settings.redis_job_queue_key, timeout=timeout_seconds)
    if not item:
        return None
    return item[1]
