import pytest

from drug_checker.sms_provider import MockSmsProvider, send_findings_reply


FINDINGS = {
    "status": "not_found",
    "query_type": "name",
    "query": "synthetic example",
    "matches": [],
    "alerts": [],
    "alert_data_status": {"status": "unknown"},
}


def test_mock_sms_provider_sends_formatted_reply_without_external_delivery():
    provider = MockSmsProvider()
    result = send_findings_reply(provider, "+2348000000000", FINDINGS)
    assert result.status == "sent"
    assert result.provider_message_id == "mock-1"
    assert len(provider.sent) == 1
    assert len(provider.sent[0]["text"]) <= 160
    assert "alert data" in provider.sent[0]["text"].casefold()


def test_mock_sms_timeout_is_reported_as_uncertain_and_not_retried():
    provider = MockSmsProvider(failure="timeout")
    result = send_findings_reply(provider, "+2348000000000", FINDINGS)
    assert result.status == "unknown"
    assert result.error_code == "timeout"
    assert provider.sent == []


def test_mock_sms_failure_is_sanitized():
    provider = MockSmsProvider(failure="error")
    result = send_findings_reply(provider, "+2348000000000", FINDINGS)
    assert result.status == "failed"
    assert result.error_code == "provider_error"
    assert "mock provider failure" not in str(result)


def test_sms_sender_rejects_empty_destination_and_clips_long_reply():
    provider = MockSmsProvider()
    with pytest.raises(ValueError):
        send_findings_reply(provider, " ", FINDINGS)
    long_findings = {**FINDINGS, "query": "synthetic " * 100}
    result = send_findings_reply(provider, "+2348000000000", long_findings)
    assert result.status == "sent"
    assert len(provider.sent[-1]["text"]) <= 160
