"""Provider-neutral outbound SMS contract and safe mock implementation.

No network transport is configured here. A real provider adapter must be
selected and configured before any real SMS can be sent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from .sms_replies import build_sms

logger = logging.getLogger(__name__)


class SmsProvider(Protocol):
    """Minimal interface implemented by a future provider adapter."""

    def send_sms(self, destination: str, text: str, timeout_seconds: float) -> str | None:
        """Send one SMS and return its provider message identifier, if any."""
        ...


@dataclass(frozen=True)
class SmsDeliveryResult:
    status: str  # sent, failed, or unknown (timeout outcome is uncertain)
    provider_message_id: str | None = None
    error_code: str | None = None


def send_findings_reply(
    provider: SmsProvider,
    destination: str,
    findings: dict,
    *,
    timeout_seconds: float = 10.0,
) -> SmsDeliveryResult:
    """Format and send a reply, returning sanitized delivery status only."""
    if not isinstance(destination, str) or not destination.strip():
        raise ValueError("destination must be a non-empty string")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    reply = build_sms(findings)
    try:
        message_id = provider.send_sms(destination, reply, timeout_seconds)
        return SmsDeliveryResult("sent", provider_message_id=message_id)
    except TimeoutError:
        # A timeout does not prove the provider failed to deliver; do not retry
        # automatically because that could send a duplicate message.
        logger.warning("SMS provider request timed out; delivery outcome unknown")
        return SmsDeliveryResult("unknown", error_code="timeout")
    except Exception:
        # Provider exceptions may include credentials, recipient numbers or
        # response bodies. Keep details out of logs and user-facing results.
        logger.error("SMS provider send failed")
        return SmsDeliveryResult("failed", error_code="provider_error")


class MockSmsProvider:
    """In-memory provider for tests; it never makes a network request."""

    def __init__(self, *, failure: str | None = None):
        if failure not in {None, "error", "timeout"}:
            raise ValueError("failure must be None, 'error', or 'timeout'")
        self.failure = failure
        self.sent = []

    def send_sms(self, destination: str, text: str, timeout_seconds: float) -> str | None:
        if self.failure == "timeout":
            raise TimeoutError
        if self.failure == "error":
            raise RuntimeError("mock provider failure")
        self.sent.append({"destination": destination, "text": text})
        return f"mock-{len(self.sent)}"
