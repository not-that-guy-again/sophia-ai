import logging
import uuid

import httpx

from sophia.services.notification import (
    NotificationMessage,
    NotificationRecipient,
    NotificationResult,
    NotificationService,
)

logger = logging.getLogger(__name__)


class WebhookNotificationService(NotificationService):
    """Notification service that POSTs JSON to a configured URL."""

    def __init__(self, webhook_url: str, timeout: float = 10.0):
        self.webhook_url = webhook_url
        self.timeout = timeout

    async def send_notification(
        self,
        recipient: NotificationRecipient,
        message: NotificationMessage,
    ) -> NotificationResult:
        payload = {
            "customer_id": recipient.customer_id,
            "email": recipient.email,
            "phone": recipient.phone,
            "channel": recipient.channel_preference,
            "subject": message.subject,
            "body": message.body,
            "source_event": message.source_event,
            "metadata": message.metadata,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.webhook_url, json=payload)
                if resp.is_success:
                    return NotificationResult(
                        success=True,
                        channel="webhook",
                        message_id=uuid.uuid4().hex[:8],
                    )
                return NotificationResult(
                    success=False,
                    channel="webhook",
                    failure_reason=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )
        except Exception as exc:
            logger.exception("Webhook notification failed")
            return NotificationResult(
                success=False,
                channel="webhook",
                failure_reason=str(exc),
            )

    async def get_channels(self) -> list[str]:
        return ["webhook"]
