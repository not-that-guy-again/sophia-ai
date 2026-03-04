import time
from unittest.mock import patch

from sophia.auth.rate_limiter import RateLimiter


def test_rate_limiter_within_limit():
    limiter = RateLimiter()
    for _ in range(5):
        assert limiter.check("key1", limit_rpm=10) is True


def test_rate_limiter_exceeded():
    limiter = RateLimiter()
    for _ in range(3):
        limiter.check("key1", limit_rpm=3)
    assert limiter.check("key1", limit_rpm=3) is False


def test_rate_limiter_different_keys():
    limiter = RateLimiter()
    for _ in range(3):
        limiter.check("key1", limit_rpm=3)
    # key2 should still be allowed
    assert limiter.check("key2", limit_rpm=3) is True


def test_rate_limiter_window_expires():
    limiter = RateLimiter()
    # Fill the window
    for _ in range(3):
        limiter.check("key1", limit_rpm=3)
    assert limiter.check("key1", limit_rpm=3) is False

    # Simulate time passing beyond 60s window
    with patch.object(time, "time", return_value=time.time() + 61):
        assert limiter.check("key1", limit_rpm=3) is True
