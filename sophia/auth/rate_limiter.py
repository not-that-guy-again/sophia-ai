import time


class RateLimiter:
    """In-memory sliding window rate limiter."""

    def __init__(self):
        self._windows: dict[str, list[float]] = {}

    def check(self, key_id: str, limit_rpm: int) -> bool:
        """Return True if the request is within the rate limit."""
        now = time.time()
        window_start = now - 60.0

        if key_id not in self._windows:
            self._windows[key_id] = []

        # Clean old entries
        self._windows[key_id] = [t for t in self._windows[key_id] if t > window_start]

        if len(self._windows[key_id]) >= limit_rpm:
            return False

        self._windows[key_id].append(now)
        return True
