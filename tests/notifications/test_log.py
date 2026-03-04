import pytest

from sophia.notifications.log import LogNotificationService
from sophia.services.notification import NotificationMessage, NotificationRecipient


@pytest.mark.asyncio
async def test_log_notification_returns_success():
    svc = LogNotificationService()
    result = await svc.send_notification(
        recipient=NotificationRecipient(
            customer_id="cust-1",
            email="test@example.com",
        ),
        message=NotificationMessage(
            body="Your order has shipped!",
            subject="Order Update",
        ),
    )
    assert result.success is True
    assert result.channel == "log"
    assert result.message_id is not None


@pytest.mark.asyncio
async def test_log_get_channels():
    svc = LogNotificationService()
    channels = await svc.get_channels()
    assert channels == ["log"]
