import time
import threading
from collections import defaultdict, deque

class InMemoryRateLimiter:
    def __init__(self):
        self.hits = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        now = time.time()
        with self.lock:
            dq = self.hits[key]
            while dq and dq[0] <= now - window_seconds:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            return True

rate_limiter = InMemoryRateLimiter()
