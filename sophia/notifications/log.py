import logging
import uuid

from sophia.services.notification import (
    NotificationMessage,
    NotificationRecipient,
    NotificationResult,
    NotificationService,
)

logger = logging.getLogger(__name__)


class LogNotificationService(NotificationService):
    """Development notification service that logs to INFO."""

    async def send_notification(
        self,
        recipient: NotificationRecipient,
        message: NotificationMessage,
    ) -> NotificationResult:
        logger.info(
            "Notification to %s (%s): subject=%s body=%s",
            recipient.customer_id,
            recipient.channel_preference,
            message.subject,
            message.body[:200],
        )
        return NotificationResult(
            success=True,
            channel="log",
            message_id=uuid.uuid4().hex[:8],
        )

    async def get_channels(self) -> list[str]:
        return ["log"]
