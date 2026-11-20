"""Offline tests for sanitised Gemini photo-read failures."""

from __future__ import annotations

import pytest
from google.genai.errors import APIError

from src.gemini import GeminiClient, classify_api_error
from src.photo import PhotoFields, PhotoReadError, extract_photo_fields

SECRET_SENTINEL = "SENTINEL_API_KEY_MUST_NOT_LEAK"


class _FailingModels:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def generate_content(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise self._error


class _FailingSDKClient:
    def __init__(self, error: Exception) -> None:
        self.models = _FailingModels(error)


@pytest.mark.parametrize(
    ("code", "kind"),
    [
        (400, "invalid_request"),
        (401, "authentication_failure"),
        (429, "rate_limit"),
        (503, "upstream_temporary"),
    ],
)
def test_api_errors_are_classified(code: int, kind: str) -> None:
    error = APIError(code, "SOME_STATUS", f"request used {SECRET_SENTINEL}")
    classified_kind, classified_code, _ = classify_api_error(error)
    assert classified_kind == kind
    assert classified_code == code
    assert SECRET_SENTINEL not in classified_kind


def test_read_photo_raises_sanitised_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = GeminiClient(force_mock=False, api_key=SECRET_SENTINEL)
    error = APIError(429, "RESOURCE_EXHAUSTED", f"key={SECRET_SENTINEL}")
    monkeypatch.setattr(client, "_get_client", lambda: _FailingSDKClient(error))

    with pytest.raises(PhotoReadError) as raised:
        client.read_photo(b"fake-image-bytes", "image/png")

    assert raised.value.kind == "rate_limit"
    assert raised.value.code == 429
    assert SECRET_SENTINEL not in raised.value.detail
    assert SECRET_SENTINEL not in str(raised.value)


def test_extract_photo_fields_never_fabricates_after_api_failure() -> None:
    class RaisingClient:
        available = True

        def read_photo(self, image_bytes: bytes, mime_type: str) -> dict[str, str]:
            raise PhotoReadError("upstream_temporary", code=503, status="UNAVAILABLE")

    result = extract_photo_fields(b"fake-image-bytes", "image/png", client=RaisingClient())

    assert result.status == "error"
    assert result.fields == PhotoFields()
    assert result.accuracy_tested is False
    assert "upstream_temporary" in result.message
    assert "503" in result.message
    assert SECRET_SENTINEL not in result.message


def test_invalid_photo_response_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    class BadResponse:
        text = '{"brand_name": ["not", "a", "string"]}'

    class BadModels:
        def generate_content(self, *args, **kwargs):  # noqa: ANN002, ANN003
            return BadResponse()

    class BadSDKClient:
        models = BadModels()

    client = GeminiClient(force_mock=False, api_key=SECRET_SENTINEL)
    monkeypatch.setattr(client, "_get_client", lambda: BadSDKClient())

    with pytest.raises(PhotoReadError) as raised:
        client.read_photo(b"fake-image-bytes", "image/png")

    assert raised.value.kind == "invalid_response"
    assert SECRET_SENTINEL not in raised.value.detail
