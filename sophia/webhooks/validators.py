"""Webhook signature validators."""

import hashlib
import hmac
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SignatureValidator(ABC):
    """Validates a webhook request signature against a shared secret."""

    @abstractmethod
    def validate(self, body: bytes, headers: dict[str, str]) -> bool:
        """Return True if the signature is valid."""
        ...


class ShopifySignatureValidator(SignatureValidator):
    """HMAC-SHA256 validation for Shopify webhooks.

    Shopify sends the HMAC digest in the X-Shopify-Hmac-Sha256 header,
    computed over the raw request body using the shared secret.
    """

    def __init__(self, secret: str):
        self.secret = secret

    def validate(self, body: bytes, headers: dict[str, str]) -> bool:
        sent_hmac = headers.get("x-shopify-hmac-sha256", "")
        if not sent_hmac:
            logger.warning("Missing X-Shopify-Hmac-Sha256 header")
            return False

        import base64

        computed = base64.b64encode(
            hmac.new(self.secret.encode(), body, hashlib.sha256).digest()
        ).decode()
        return hmac.compare_digest(computed, sent_hmac)


class NoopValidator(SignatureValidator):
    """Always-pass validator for development / testing."""

    def validate(self, body: bytes, headers: dict[str, str]) -> bool:
        return True
