import httpx
import pytest

from sophia.notifications.webhook_notifier import WebhookNotificationService
from sophia.services.notification import NotificationMessage, NotificationRecipient


def _make_recipient():
    return NotificationRecipient(customer_id="cust-1", email="test@example.com")


def _make_message():
    return NotificationMessage(body="Hello!", subject="Test")


@pytest.mark.asyncio
async def test_webhook_notification_success(monkeypatch):
    async def mock_post(self, url, **kwargs):
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    svc = WebhookNotificationService(webhook_url="http://hooks.test/notify")
    result = await svc.send_notification(_make_recipient(), _make_message())

    assert result.success is True
    assert result.channel == "webhook"


@pytest.mark.asyncio
async def test_webhook_notification_failure(monkeypatch):
    async def mock_post(self, url, **kwargs):
        return httpx.Response(500, text="Internal Server Error")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    svc = WebhookNotificationService(webhook_url="http://hooks.test/notify")
    result = await svc.send_notification(_make_recipient(), _make_message())

    assert result.success is False
    assert result.channel == "webhook"
    assert "500" in result.failure_reason


@pytest.mark.asyncio
async def test_webhook_get_channels():
    svc = WebhookNotificationService(webhook_url="http://hooks.test/notify")
    channels = await svc.get_channels()
    assert channels == ["webhook"]
