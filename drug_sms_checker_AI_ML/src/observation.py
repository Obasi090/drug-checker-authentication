"""Common observation model and adapters for SMS and packaging OCR.

An observation is an input to verification, never an expected/ground-truth
value. Missing, unreadable (``NOT_VISIBLE``) and conflicting fields are kept as
distinct states. Package volume is a separate field from medicine strength.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .message import MessageIntent
from .photo import PhotoFields, PhotoResult, is_missing

SourceChannel = Literal["sms", "daylight_ocr", "indoor_ocr", "consolidated_ocr"]
FieldAvailability = Literal["PRESENT", "MISSING", "NOT_VISIBLE", "CONFLICT"]

SOURCE_CHANNELS: tuple[str, ...] = (
    "sms",
    "daylight_ocr",
    "indoor_ocr",
    "consolidated_ocr",
)
OBSERVED_FIELDS: tuple[str, ...] = (
    "registration_number",
    "brand_name",
    "generic_name",
    "manufacturer",
    "strength",
    "dosage_form",
    "package_volume",
)
SEARCHABLE_FIELDS: tuple[str, ...] = (
    "registration_number",
    "brand_name",
    "generic_name",
)


class ObservedField(BaseModel):
    """One observed value plus its availability and raw original text."""

    model_config = ConfigDict(extra="forbid")

    value: str | None = None
    raw: str | None = None
    status: FieldAvailability = "MISSING"
    provenance: str = ""

    @classmethod
    def present(cls, value: str | None, provenance: str = "") -> "ObservedField":
        text = "" if value is None else str(value)
        if is_missing(text):
            return cls(value=None, raw=text, status="NOT_VISIBLE", provenance=provenance)
        return cls(value=text, raw=text, status="PRESENT", provenance=provenance)

    @classmethod
    def missing(cls, provenance: str = "") -> "ObservedField":
        return cls(value=None, raw=None, status="MISSING", provenance=provenance)

    @classmethod
    def not_visible(cls, raw: str | None = None, provenance: str = "") -> "ObservedField":
        return cls(value=None, raw=raw, status="NOT_VISIBLE", provenance=provenance)

    @classmethod
    def conflict(cls, daylight: str | None, indoor: str | None,
                 provenance: str = "") -> "ObservedField":
        raw = f"{daylight or ''} || {indoor or ''}"
        return cls(value=None, raw=raw, status="CONFLICT", provenance=provenance)

    @property
    def usable(self) -> bool:
        return self.status == "PRESENT" and bool(self.value)


class MedicineObservation(BaseModel):
    """Channel-neutral medicine observation for the verification engine."""

    model_config = ConfigDict(extra="forbid")

    observation_id: str
    source_channel: SourceChannel
    brand_name: ObservedField = Field(default_factory=ObservedField)
    generic_name: ObservedField = Field(default_factory=ObservedField)
    registration_number: ObservedField = Field(default_factory=ObservedField)
    manufacturer: ObservedField = Field(default_factory=ObservedField)
    strength: ObservedField = Field(default_factory=ObservedField)
    dosage_form: ObservedField = Field(default_factory=ObservedField)
    package_volume: ObservedField = Field(default_factory=ObservedField)

    source_field_statuses: dict[str, str] = Field(default_factory=dict)
    source_manual_review_required: bool = False
    source_manual_review_fields: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    accuracy_tested: bool = False
    notes: list[str] = Field(default_factory=list)

    def field(self, name: str) -> ObservedField:
        try:
            value = getattr(self, name)
        except AttributeError as exc:
            raise KeyError(f"unknown observation field: {name}") from exc
        if not isinstance(value, ObservedField):
            raise KeyError(f"not an observed field: {name}")
        return value

    def present_fields(self) -> list[str]:
        return [name for name in OBSERVED_FIELDS if self.field(name).usable]

    def searchable_fields(self) -> list[str]:
        return [name for name in SEARCHABLE_FIELDS if self.field(name).usable]

    def conflict_fields(self) -> list[str]:
        return [name for name in OBSERVED_FIELDS if self.field(name).status == "CONFLICT"]

    @classmethod
    def from_message_intent(
        cls,
        intent: MessageIntent,
        *,
        observation_id: str = "SMS-1",
        provenance: dict[str, Any] | None = None,
    ) -> "MedicineObservation":
        """Adapt existing deterministic/extracted SMS parser output."""
        extra = dict(provenance or {})
        base_provenance: dict[str, Any] = {
            "source": "src.message.parse_message",
            "original": intent.original,
            "normalized": intent.normalized,
            "intent": intent.intent,
            "extracted_by": intent.extracted_by,
            "parser_notes": list(intent.notes),
        }
        base_provenance.update(extra)
        return cls(
            observation_id=observation_id,
            source_channel="sms",
            brand_name=ObservedField.present(intent.name, provenance="MessageIntent.name"),
            registration_number=ObservedField.present(
                intent.registration_number, provenance="MessageIntent.registration_number"
            ),
            provenance=base_provenance,
            notes=list(intent.notes),
        )

    @classmethod
    def from_photo_fields(
        cls,
        fields: PhotoFields,
        *,
        channel: SourceChannel = "consolidated_ocr",
        observation_id: str = "PHOTO-1",
        provenance: dict[str, Any] | None = None,
        photo_status: str = "",
        photo_message: str = "",
    ) -> "MedicineObservation":
        """Adapt raw four-field photo extraction output."""
        if channel not in SOURCE_CHANNELS:
            raise ValueError(f"unsupported source channel: {channel}")
        base_provenance: dict[str, Any] = {
            "source": "src.photo.PhotoFields",
            "photo_status": photo_status,
            "photo_message": photo_message,
        }
        base_provenance.update(provenance or {})
        return cls(
            observation_id=observation_id,
            source_channel=channel,
            brand_name=ObservedField.present(fields.brand_name, "PhotoFields.brand_name"),
            registration_number=ObservedField.present(
                fields.registration_number, "PhotoFields.registration_number"
            ),
            manufacturer=ObservedField.present(fields.manufacturer, "PhotoFields.manufacturer"),
            strength=ObservedField.present(fields.strength, "PhotoFields.strength"),
            source_field_statuses={
                name: "RAW_PHOTO_FIELD"
                for name in ("brand_name", "registration_number", "manufacturer", "strength")
            },
            provenance=base_provenance,
            notes=["Photo fields are observations only; OCR accuracy is NOT TESTED."],
        )

    @classmethod
    def from_photo_result(
        cls,
        result: PhotoResult,
        *,
        channel: SourceChannel = "consolidated_ocr",
        observation_id: str = "PHOTO-1",
        provenance: dict[str, Any] | None = None,
    ) -> "MedicineObservation":
        return cls.from_photo_fields(
            result.fields,
            channel=channel,
            observation_id=observation_id,
            provenance=provenance,
            photo_status=result.status,
            photo_message=result.message,
        )

    @classmethod
    def from_image_level_ocr_row(
        cls,
        row: dict[str, str],
        *,
        channel: SourceChannel,
        observation_id: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> "MedicineObservation":
        """Adapt one pre-reconciliation OCR row from ``ocr_results.csv``."""
        if channel not in {"daylight_ocr", "indoor_ocr"}:
            raise ValueError(f"image-level OCR requires daylight_ocr or indoor_ocr, got {channel}")
        medicine_id = str(row.get("medicine_id", "") or "").strip()
        base_provenance: dict[str, Any] = {
            "source": "data/packaging/ocr_results.csv",
            "medicine_id": medicine_id,
            "image_condition": row.get("image_condition", ""),
            "image_filename": row.get("image_filename", ""),
        }
        base_provenance.update(provenance or {})
        return cls(
            observation_id=observation_id or f"OCR-{medicine_id or 'unknown'}-{channel}",
            source_channel=channel,
            brand_name=ObservedField.present(row.get("brand_name"), "ocr_results.brand_name"),
            registration_number=ObservedField.present(
                row.get("nafdac_registration_number"),
                "ocr_results.nafdac_registration_number",
            ),
            manufacturer=ObservedField.present(row.get("manufacturer"), "ocr_results.manufacturer"),
            strength=ObservedField.present(row.get("strength"), "ocr_results.strength"),
            package_volume=ObservedField.present(
                row.get("package_volume_separate_from_strength"),
                "ocr_results.package_volume_separate_from_strength",
            ),
            source_field_statuses={name: "RAW_OCR" for name in OBSERVED_FIELDS},
            provenance=base_provenance,
            notes=["Raw OCR text is an observation only; not independently verified."],
        )

    @classmethod
    def from_package_result(
        cls,
        row: dict[str, str],
        *,
        observation_id: str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> "MedicineObservation":
        """Adapt one reconciled row from ``package_results.csv``.

        Existing daylight/indoor reconciliation statuses are preserved in
        ``source_field_statuses``. A genuine OCR ``CONFLICT`` becomes a
        ``CONFLICT`` observation field; the competing raw values are retained
        and the conflict marker itself is never used as a value.
        """
        def adapt_field(
            logical_name: str,
            value_key: str,
            status_key: str,
            day_key: str | None = None,
            indoor_key: str | None = None,
        ) -> ObservedField:
            raw_status = str(row.get(status_key, "") or "").strip().upper()
            value = str(row.get(value_key, "") or "")
            day_value = str(row.get(day_key, "") or "") if day_key else ""
            indoor_value = str(row.get(indoor_key, "") or "") if indoor_key else ""

            if raw_status == "CONFLICT" or value.strip().upper() == "CONFLICT":
                return ObservedField.conflict(day_value, indoor_value, f"package_results.{status_key}")
            if raw_status == "NOT_VISIBLE" or is_missing(value):
                return ObservedField.not_visible(value or None, f"package_results.{status_key}")
            return ObservedField.present(value, f"package_results.{status_key}")

        medicine_id = str(row.get("medicine_id", "") or "").strip()
        base_provenance: dict[str, Any] = {
            "source": "data/packaging/package_results.csv",
            "medicine_id": medicine_id,
            "package_note": row.get("notes", ""),
        }
        base_provenance.update(provenance or {})

        fields = {
            "brand_name": adapt_field(
                "brand_name", "brand_name", "brand_status",
                "brand_conflict_daylight", "brand_conflict_indoor",
            ),
            "registration_number": adapt_field(
                "registration_number", "nafdac_registration_number", "registration_status",
                "registration_conflict_daylight", "registration_conflict_indoor",
            ),
            "manufacturer": adapt_field(
                "manufacturer", "manufacturer", "manufacturer_status",
                "manufacturer_conflict_daylight", "manufacturer_conflict_indoor",
            ),
            "strength": adapt_field(
                "strength", "strength", "strength_status",
                "strength_conflict_daylight", "strength_conflict_indoor",
            ),
            "package_volume": adapt_field(
                "package_volume", "package_volume", "package_volume_status",
                "package_volume_daylight", "package_volume_indoor",
            ),
        }
        status_columns = {
            "brand_name": "brand_status",
            "registration_number": "registration_status",
            "manufacturer": "manufacturer_status",
            "strength": "strength_status",
            "package_volume": "package_volume_status",
        }
        source_statuses = {
            name: str(row.get(column, "") or "").strip().upper()
            for name, column in status_columns.items()
        }
        review_text = str(row.get("manual_review_fields", "") or "").strip()
        review_fields = [item.strip() for item in review_text.split(";") if item.strip()]

        return cls(
            observation_id=observation_id or f"PACK-{medicine_id or 'unknown'}",
            source_channel="consolidated_ocr",
            brand_name=fields["brand_name"],
            registration_number=fields["registration_number"],
            manufacturer=fields["manufacturer"],
            strength=fields["strength"],
            package_volume=fields["package_volume"],
            source_field_statuses=source_statuses,
            source_manual_review_required=str(
                row.get("manual_review_required", "") or ""
            ).strip().casefold() == "true",
            source_manual_review_fields=review_fields,
            provenance=base_provenance,
            notes=[
                "Reconciled OCR is an observation only; ground truth is empty.",
                "Real-pack OCR accuracy remains NOT TESTED.",
            ],
        )


def observation_from_sms_text(
    text: str,
    known_names: list[str] | tuple[str, ...],
    *,
    observation_id: str = "SMS-1",
) -> MedicineObservation:
    """Convenience adapter: parse an SMS with existing code, then adapt it."""
    from .message import parse_message  # imported lazily to keep the seam explicit

    return MedicineObservation.from_message_intent(
        parse_message(text, list(known_names)), observation_id=observation_id
    )
