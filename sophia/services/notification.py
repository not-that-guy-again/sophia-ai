from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class NotificationRecipient:
    customer_id: str
    email: str | None = None
    phone: str | None = None
    channel_preference: str = "email"


@dataclass
class NotificationMessage:
    body: str
    subject: str | None = None
    source_event: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class NotificationResult:
    success: bool
    channel: str
    message_id: str | None = None
    failure_reason: str | None = None


class NotificationService(ABC):
    @abstractmethod
    async def send_notification(
        self,
        recipient: NotificationRecipient,
        message: NotificationMessage,
    ) -> NotificationResult: ...

    @abstractmethod
    async def get_channels(self) -> list[str]: ...
