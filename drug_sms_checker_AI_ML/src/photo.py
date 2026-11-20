"""Safe package-photo interface.

Real packaging images now exist under ``data/packaging/``, but the independent
verification fields in ``ground_truth.csv`` are empty. Live OCR accuracy is
therefore explicitly NOT TESTED and no extraction may be shown as validated.
Uploaded bytes are processed in memory and never written to disk or retained
after the call.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, ValidationError

NOT_VISIBLE = "not visible"
MISSING_TOKENS = {"", "not visible", "not visible.", "n/a", "na", "none", "null"}
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_BYTES = 5 * 1024 * 1024


def is_missing(value: str | None) -> bool:
    """True when a value semantically means 'not visible'/absent.

    Empty strings, nulls and the literal ``Not visible`` from the OCR CSVs are
    the same semantic state. The raw image-level text is preserved separately.
    """
    if value is None:
        return True
    return str(value).strip().casefold() in MISSING_TOKENS


class PhotoReadError(RuntimeError):
    """Sanitised photo-reading failure; never carries credentials or raw bodies."""

    def __init__(self, kind: str, *, code: int | str | None = None,
                 status: str | None = None) -> None:
        self.kind = kind
        self.code = code
        self.status = status
        parts = [kind]
        if code is not None:
            parts.append(f"code={code}")
        if status:
            parts.append(f"status={status}")
        super().__init__("; ".join(parts))

    @property
    def detail(self) -> str:
        return str(self)


class PhotoFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brand_name: str = NOT_VISIBLE
    registration_number: str = NOT_VISIBLE
    manufacturer: str = NOT_VISIBLE
    strength: str = NOT_VISIBLE


class PhotoResult(BaseModel):
    fields: PhotoFields
    status: str  # ok | rejected | NOT TESTED | error
    accuracy_tested: bool = False
    message: str = ""


class PhotoTestRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id: str
    lighting: str
    image_path: str = ""
    expected_registration_number: str = ""
    observed_registration_number: str = NOT_VISIBLE
    result: str = "pending"
    notes: str = ""


def validate_upload(content_type: str | None, size_bytes: int) -> str | None:
    """Return an error message, or None when the upload is acceptable."""
    if content_type not in ALLOWED_TYPES:
        return f"Unsupported image type: {content_type}. Use JPEG, PNG or WebP."
    if size_bytes <= 0:
        return "The image is empty."
    if size_bytes > MAX_BYTES:
        return f"The image is larger than {MAX_BYTES // (1024 * 1024)} MB."
    return None


def extract_photo_fields(image_bytes: bytes, mime_type: str, client=None) -> PhotoResult:
    """Extract four fields only. No guessing, no retention, no status decision."""
    error = validate_upload(mime_type, len(image_bytes))
    if error:
        return PhotoResult(fields=PhotoFields(), status="rejected", message=error)

    if client is None or not getattr(client, "available", False):
        result = PhotoResult(
            fields=PhotoFields(),
            status="NOT TESTED",
            message=("Photo reading is disabled: no configured Gemini client. "
                     "Real-pack OCR accuracy is NOT TESTED; do not use live OCR in the demo."),
        )
    else:
        try:
            raw = client.read_photo(image_bytes, mime_type)
            result = PhotoResult(
                fields=PhotoFields.model_validate(raw),
                status="ok",
                message=("Values must be shown for user edit/confirmation before any backend lookup. "
                         "Real-pack OCR accuracy remains NOT TESTED."),
            )
        except PhotoReadError as exc:
            result = PhotoResult(fields=PhotoFields(), status="error",
                                 message=f"Photo read failed: {exc.detail}")
        except (ValidationError, ValueError, OSError, RuntimeError) as exc:
            result = PhotoResult(fields=PhotoFields(), status="error",
                                 message=f"Photo read failed: {type(exc).__name__}")
        except Exception:  # noqa: BLE001 - never leak a raw body or a guessed value
            result = PhotoResult(fields=PhotoFields(), status="error",
                                 message="Photo read failed: unexpected error")

    del image_bytes  # do not retain upload data beyond this call
    return result
