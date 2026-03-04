import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class NotificationGate:
    """Gate that enforces rate limits and quiet hours for notifications."""

    def __init__(self):
        self._daily_counts: dict[str, dict[str, int]] = {}  # {customer_id: {date_str: count}}

    def check(
        self,
        customer_id: str,
        limits_config: dict | None = None,
    ) -> tuple[bool, str]:
        """Check if notification is allowed.

        Returns (allowed, reason).
        """
        config = limits_config or {}
        max_daily = config.get("max_daily_per_customer", 10)
        quiet_start = config.get("quiet_hours_start")  # e.g., 22
        quiet_end = config.get("quiet_hours_end")  # e.g., 7

        # Check quiet hours
        if quiet_start is not None and quiet_end is not None:
            now_hour = datetime.now(timezone.utc).hour
            if quiet_start > quiet_end:
                # Wraps midnight: e.g., 22-7
                in_quiet = now_hour >= quiet_start or now_hour < quiet_end
            else:
                in_quiet = quiet_start <= now_hour < quiet_end
            if in_quiet:
                return False, f"Quiet hours ({quiet_start}:00-{quiet_end}:00 UTC)"

        # Check daily rate limit
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if customer_id not in self._daily_counts:
            self._daily_counts[customer_id] = {}

        # Clean old dates
        self._daily_counts[customer_id] = {
            d: c for d, c in self._daily_counts[customer_id].items() if d == today
        }

        current = self._daily_counts[customer_id].get(today, 0)
        if current >= max_daily:
            return False, f"Daily limit exceeded ({max_daily}/day)"

        self._daily_counts[customer_id][today] = current + 1
        return True, "OK"
