"""Tiny in-process sliding-window rate limiter.

Good enough for a single replica. For horizontal scaling, move this state to Redis
(e.g. a sorted set per key) so every replica sees the same counters.
"""
import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_s: float, max_keys: int = 100_000):
        self.limit = limit
        self.window_s = window_s
        self.max_keys = max_keys
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Record a hit for `key`; return False if the key is over its limit."""
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > self.max_keys:  # crude memory bound
                self._hits.clear()
            q = self._hits[key]
            while q and now - q[0] > self.window_s:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True
