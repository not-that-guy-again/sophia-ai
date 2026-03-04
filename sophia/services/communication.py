"""Communication service interface and models.

Framework-level capability for internal team messaging (Slack, email).
The hat defines policy (who is reachable, via which channel, at which address)
in constraints.json. The framework enforces that policy at send time.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CommunicationContact:
    channel: str  # "slack" or "email"
    address: str  # Slack channel ID/#name or email address
    role: str  # "manager", "supervisor", "team", etc.


@dataclass
class CommunicationMessage:
    subject: str
    body: str
    priority: str  # "low", "medium", "high", "urgent"
    source_ticket: str | None = None


@dataclass
class CommunicationResult:
    success: bool
    channel: str
    message_id: str | None = None
    failure_reason: str | None = None


class CommunicationService(ABC):

    @abstractmethod
    async def send_to_role(
        self,
        role: str,
        message: CommunicationMessage,
    ) -> CommunicationResult:
        """Send a message to a named role. The service resolves the role
        to a channel and address using the policy it was built with."""
        ...

    @abstractmethod
    async def get_contacts(self) -> list[CommunicationContact]:
        """Return all configured contacts (for diagnostic purposes)."""
        ...
