"""Mock communication service for testing and development."""

import logging

from sophia.services.communication import (
    CommunicationContact,
    CommunicationMessage,
    CommunicationResult,
    CommunicationService,
)

logger = logging.getLogger(__name__)


class MockCommunicationService(CommunicationService):
    def __init__(self, policy: dict[str, CommunicationContact] | None = None):
        self.policy = policy or {}
        self._sent: list[tuple[str, CommunicationMessage]] = []

    async def send_to_role(
        self, role: str, message: CommunicationMessage
    ) -> CommunicationResult:
        self._sent.append((role, message))
        logger.info("Mock communication to role=%s: %s", role, message.subject)
        return CommunicationResult(
            success=True, channel="mock", message_id="MOCK-001"
        )

    async def get_contacts(self) -> list[CommunicationContact]:
        return list(self.policy.values())
