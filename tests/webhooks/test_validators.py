"""Tests for webhook signature validators."""

import base64
import hashlib
import hmac

from sophia.webhooks.validators import NoopValidator, ShopifySignatureValidator


def test_noop_validator_always_passes():
    v = NoopValidator()
    assert v.validate(b"anything", {})
    assert v.validate(b"", {"x-some-header": "value"})


def test_shopify_validator_valid_signature():
    secret = "test_secret_123"
    body = b'{"id": 12345, "email": "test@example.com"}'
    expected_hmac = base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()

    v = ShopifySignatureValidator(secret)
    headers = {"x-shopify-hmac-sha256": expected_hmac}
    assert v.validate(body, headers)


def test_shopify_validator_invalid_signature():
    secret = "test_secret_123"
    body = b'{"id": 12345}'
    v = ShopifySignatureValidator(secret)
    headers = {"x-shopify-hmac-sha256": "invalid_signature"}
    assert not v.validate(body, headers)


def test_shopify_validator_missing_header():
    v = ShopifySignatureValidator("secret")
    assert not v.validate(b"body", {})
