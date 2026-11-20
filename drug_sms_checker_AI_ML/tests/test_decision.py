"""Six-way decision tests and human-readable reason checks."""

from __future__ import annotations

from src.decision import VERIFICATION_STATUSES
from src.observation import MedicineObservation, ObservedField
from src.packaging import read_csv_rows
from src.verification import VerificationEngine

ENGINE = VerificationEngine()
PACKAGE_RESULTS = ENGINE.catalogue.source_path.replace("test_drugs.csv", "packaging/package_results.csv")


def _observation(**fields: str | ObservedField) -> MedicineObservation:
    values: dict[str, str | ObservedField | None] = {
        "brand_name": None,
        "generic_name": None,
        "registration_number": None,
        "manufacturer": None,
        "strength": None,
        "dosage_form": None,
        "package_volume": None,
    }
    values.update(fields)
    return MedicineObservation(
        observation_id="TEST",
        source_channel="sms",
        **{
            name: value if isinstance(value, ObservedField)
            else ObservedField.present(value, f"test.{name}")
            for name, value in values.items()
        },
    )


def test_match_with_exact_registration_and_corroborating_fields() -> None:
    result = ENGINE.verify(_observation(
        registration_number="B4-1180",
        brand_name="1980 Azithromycin USP 250 mg Tablets",
        generic_name="Azithromycin (Azithromycin Dihydrate)",
        manufacturer="Surmount Laboratories Pvt Ltd",
        strength="250 mg",
    ))

    assert result.status == "MATCH"
    assert result.selected_product_id is not None
    assert any("exactly selected" in reason for reason in result.reasons)
    assert any("consistent" in reason for reason in result.reasons)


def test_partial_match_for_single_exact_brand_without_independent_support() -> None:
    result = ENGINE.verify_sms("check Acimox Capsule")

    assert result.status == "PARTIAL_MATCH"
    assert len(result.candidates.candidates) == 1
    assert any("name evidence alone" in reason for reason in result.reasons)


def test_mismatch_when_registration_conflicts_with_exact_brand() -> None:
    result = ENGINE.verify(_observation(
        registration_number="ZZ-9999",
        brand_name="Acimox Capsule",
    ))

    assert result.status == "MISMATCH"
    assert any("registration number conflicts" in reason for reason in result.reasons)


def test_mismatch_when_exact_registration_has_wrong_strength() -> None:
    result = ENGINE.verify(_observation(
        registration_number="B4-1180",
        brand_name="1980 Azithromycin USP 250 mg Tablets",
        strength="500 mg",
    ))

    assert result.status == "MISMATCH"
    assert any("strength conflicts" in reason for reason in result.reasons)


def test_no_match_for_well_formed_absent_registration() -> None:
    result = ENGINE.verify_sms("check ZZ-9999")

    assert result.status == "NO_MATCH"
    assert result.candidates.candidates == []
    assert any("no catalogue candidate" in reason for reason in result.reasons)


def test_insufficient_information_for_empty_and_strength_only_input() -> None:
    empty = ENGINE.verify(_observation())
    strength_only = ENGINE.verify(_observation(strength="250 mg"))

    assert empty.status == "INSUFFICIENT_INFORMATION"
    assert strength_only.status == "INSUFFICIENT_INFORMATION"
    assert any("too little" in reason.lower() or "no usable" in reason.lower()
               for reason in empty.reasons)


def test_ocr_conflict_forces_manual_review_and_keeps_raw_values() -> None:
    rows = read_csv_rows(PACKAGE_RESULTS)
    pack_10 = next(row for row in rows if row["medicine_id"] == "pack_10")
    result = ENGINE.verify_package_row(pack_10)

    assert result.status == "MANUAL_REVIEW_REQUIRED"
    assert "brand_name" in result.review_fields
    assert any("genuine conflict" in reason for reason in result.reasons)
    assert result.accuracy_tested is False
    day = pack_10["brand_conflict_daylight"]
    assert day in " ".join(result.reasons)


def test_generic_collision_requires_manual_review_and_returns_all_products() -> None:
    result = ENGINE.verify(_observation(generic_name="Paracetamol"))

    assert result.status == "MANUAL_REVIEW_REQUIRED"
    assert len(result.candidates.candidates) == 2
    assert {item.product.registration_number for item in result.candidates.candidates} == {
        "A11-0131", "A4-0704",
    }


def test_fuzzy_suggestion_never_becomes_a_verification_match() -> None:
    result = ENGINE.verify_sms("check Ablept 300 Capusles")

    assert result.status == "MANUAL_REVIEW_REQUIRED"
    assert result.candidates.selected is not None
    assert result.candidates.selected.similarity_score is not None
    assert any("fuzzy suggestion" in reason for reason in result.reasons)
    assert any("not accepted as identity evidence" in reason for reason in result.reasons)


def test_exact_registration_with_similar_brand_is_partial_not_invented_match() -> None:
    result = ENGINE.verify(_observation(
        registration_number="B4-9460",
        brand_name="Ablept 300 Capusles",
    ))

    assert result.status == "PARTIAL_MATCH"
    assert result.selected_product_id is not None
    brand_row = result.field_comparisons[result.selected_product_id][1]
    assert brand_row.similarity_score is not None
    assert any("similarity_score=" in reason for reason in result.reasons)


def test_unparsed_observed_field_requires_review() -> None:
    result = ENGINE.verify(_observation(
        registration_number="04-0858",
        brand_name="10% Dextrose (500/1000 mL)",
        package_volume="about a bottle",
    ))

    assert result.status == "MANUAL_REVIEW_REQUIRED"
    assert "package_volume" in result.review_fields
    assert any("could not be parsed safely" in reason for reason in result.reasons)


def test_all_six_statuses_and_no_confidence_values() -> None:
    results = [
        ENGINE.verify(_observation(
            registration_number="B4-1180",
            brand_name="1980 Azithromycin USP 250 mg Tablets",
            strength="250 mg",
        )),
        ENGINE.verify_sms("check Acimox Capsule"),
        ENGINE.verify(_observation(registration_number="ZZ-9999", brand_name="Acimox Capsule")),
        ENGINE.verify_sms("check ZZ-9999"),
        ENGINE.verify(_observation()),
        ENGINE.verify_sms("check Ablept 300 Capusles"),
    ]

    assert {result.status for result in results} == set(VERIFICATION_STATUSES)
    for result in results:
        assert result.reasons
        assert result.status_explanation
        dumped = result.model_dump()
        assert "confidence" not in dumped
        assert "probability" not in dumped
        assert all("%" not in reason for reason in result.reasons)
