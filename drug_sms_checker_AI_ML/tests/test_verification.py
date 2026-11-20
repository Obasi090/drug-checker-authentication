"""Integration tests for the offline verification facade and input adapters."""

from __future__ import annotations

from pathlib import Path

from src.contracts import AWAITING_BACKEND_CONFIRMATION
from src.message import parse_message
from src.observation import MedicineObservation
from src.photo import PhotoFields, PhotoResult
from src.verification import VerificationEngine

ENGINE = VerificationEngine()
ROOT = Path(__file__).resolve().parents[1]
PACKAGE_RESULTS = ROOT / "data" / "packaging" / "package_results.csv"


def test_sms_adapter_preserves_original_message_and_provenance() -> None:
    intent = parse_message("abeg check B4-1180 please", ENGINE.catalogue.brand_names)
    observation = MedicineObservation.from_message_intent(intent)

    assert observation.source_channel == "sms"
    assert observation.field("registration_number").value == "B4-1180"
    assert observation.provenance["original"] == "abeg check B4-1180 please"
    assert observation.provenance["source"] == "src.message.parse_message"
    assert observation.accuracy_tested is False

    result = ENGINE.verify(observation)
    assert result.status == "MATCH"
    assert result.candidates.selected is not None
    assert result.candidates.selected.product.registration_number == "B4-1180"


def test_photo_adapter_keeps_ocr_as_unverified_observation() -> None:
    photo_result = PhotoResult(
        fields=PhotoFields(
            brand_name="Acimox Capsule",
            registration_number="A4-8982",
            manufacturer="A.C. Drugs Ltd",
            strength="not visible",
        ),
        status="NOT TESTED",
        message="OCR output must be confirmed by a user.",
    )
    observation = MedicineObservation.from_photo_result(photo_result)
    result = ENGINE.verify(observation)

    assert observation.source_channel == "consolidated_ocr"
    assert observation.field("brand_name").value == "Acimox Capsule"
    assert observation.field("strength").status == "NOT_VISIBLE"
    assert observation.provenance["photo_status"] == "NOT TESTED"
    assert result.accuracy_tested is False
    assert any("OCR values are observations only" in note for note in result.notes)
    assert result.status in {"MATCH", "PARTIAL_MATCH", "MANUAL_REVIEW_REQUIRED"}


def test_package_adapter_preserves_reconciliation_statuses() -> None:
    row = {
        "medicine_id": "synthetic_pack",
        "brand_name": "CONFLICT",
        "brand_status": "CONFLICT",
        "brand_conflict_daylight": "Brand A",
        "brand_conflict_indoor": "Brand B",
        "nafdac_registration_number": "04-9999",
        "registration_status": "DAYLIGHT_ONLY",
        "manufacturer": "not visible",
        "manufacturer_status": "NOT_VISIBLE",
        "strength": "not visible",
        "strength_status": "NOT_VISIBLE",
        "package_volume": "20 ml",
        "package_volume_status": "INDOOR_ONLY",
        "manual_review_required": "true",
        "manual_review_fields": "brand_name",
        "notes": "synthetic conflict",
    }
    observation = MedicineObservation.from_package_result(row)

    assert observation.field("brand_name").status == "CONFLICT"
    assert observation.field("brand_name").value is None
    assert "Brand A || Brand B" == observation.field("brand_name").raw
    assert observation.source_field_statuses["registration_number"] == "DAYLIGHT_ONLY"
    assert observation.source_field_statuses["package_volume"] == "INDOOR_ONLY"
    assert observation.source_manual_review_required is True
    assert observation.field("package_volume").value == "20 ml"
    assert ENGINE.verify(observation).status == "MANUAL_REVIEW_REQUIRED"


def test_packaging_batch_has_no_forced_match() -> None:
    before = PACKAGE_RESULTS.read_bytes()
    results = ENGINE.verify_package_results(PACKAGE_RESULTS)

    assert len(results) == 11
    assert all(result.status in {"NO_MATCH", "MANUAL_REVIEW_REQUIRED"} for result in results)
    assert not any(result.status == "MATCH" for result in results)

    by_id = {result.observation_id: result for result in results}
    assert by_id["PACK-pack_02"].status == "NO_MATCH"
    assert by_id["PACK-pack_10"].status == "MANUAL_REVIEW_REQUIRED"
    assert PACKAGE_RESULTS.read_bytes() == before


def test_result_is_internal_and_contract_remains_unconfirmed() -> None:
    result = ENGINE.verify_sms("check B4-1180")
    dumped = result.model_dump()

    assert AWAITING_BACKEND_CONFIRMATION is True
    assert "confidence" not in dumped
    assert "alerts" not in dumped
    assert "data_as_of" not in dumped
    assert result.catalogue_sha256 == ENGINE.catalogue.source_sha256
    assert result.accuracy_tested is False
