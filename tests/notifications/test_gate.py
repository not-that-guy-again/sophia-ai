from unittest.mock import patch
from datetime import datetime, timezone

from sophia.notifications.gate import NotificationGate


def test_gate_allows_within_limit():
    gate = NotificationGate()
    allowed, reason = gate.check("cust-1", {"max_daily_per_customer": 5})
    assert allowed is True
    assert reason == "OK"


def test_gate_blocks_over_limit():
    gate = NotificationGate()
    config = {"max_daily_per_customer": 3}
    for _ in range(3):
        gate.check("cust-1", config)
    allowed, reason = gate.check("cust-1", config)
    assert allowed is False
    assert "Daily limit" in reason


def test_gate_blocks_quiet_hours():
    gate = NotificationGate()
    config = {"quiet_hours_start": 22, "quiet_hours_end": 7}

    # Mock current time to 23:00 UTC (in quiet hours)
    mock_dt = datetime(2025, 3, 1, 23, 0, 0, tzinfo=timezone.utc)
    with patch("sophia.notifications.gate.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_dt
        mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
        allowed, reason = gate.check("cust-1", config)

    assert allowed is False
    assert "Quiet hours" in reason


def test_gate_allows_outside_quiet_hours():
    gate = NotificationGate()
    config = {"quiet_hours_start": 22, "quiet_hours_end": 7}

    # Mock current time to 14:00 UTC (outside quiet hours)
    mock_dt = datetime(2025, 3, 1, 14, 0, 0, tzinfo=timezone.utc)
    with patch("sophia.notifications.gate.datetime") as mock_datetime:
        mock_datetime.now.return_value = mock_dt
        mock_datetime.side_effect = lambda *a, **kw: datetime(*a, **kw)
        allowed, reason = gate.check("cust-1", config)

    assert allowed is True


def test_gate_different_customers():
    gate = NotificationGate()
    config = {"max_daily_per_customer": 1}
    gate.check("cust-1", config)
    # cust-1 is at limit, but cust-2 should still be allowed
    allowed, _ = gate.check("cust-2", config)
    assert allowed is True
