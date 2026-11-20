"""Candidate-generation tests: priority, ambiguity and fuzzy-suggestion safety."""

from __future__ import annotations

from src.candidate import generate_candidates
from src.catalogue import load_catalogue
from src.observation import MedicineObservation, ObservedField

CATALOGUE = load_catalogue()


def _observation(**fields: str) -> MedicineObservation:
    values = {
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
        **{name: ObservedField.present(value, f"test.{name}") for name, value in values.items()},
    )


def _candidates(**fields: str):
    return generate_candidates(_observation(**fields), CATALOGUE)


def test_exact_registration_lookup_is_prioritised() -> None:
    result = _candidates(
        registration_number="B4-9460",
        brand_name="Acimox Capsule",
    )

    expected = CATALOGUE.registration_lookup("B4-9460")
    assert expected is not None
    assert result.exact_registration_product_id == expected.product_id
    assert result.candidates[0].product.registration_number == "B4-9460"
    assert result.candidates[0].matched_by == "registration_number_exact"
    assert result.candidates[0].requires_confirmation is False
    assert any(item.product.registration_number == "A4-8982" for item in result.candidates)
    assert "prioritised" in " ".join(result.reasons).lower()


def test_unknown_registration_does_not_become_a_fuzzy_name_guess() -> None:
    result = _candidates(
        registration_number="ZZ-9999",
        brand_name="Acimox Capsul",
    )

    assert result.candidates == []
    assert result.fuzzy_suggestions_used is False
    assert any("suppressed" in reason.lower() for reason in result.reasons)


def test_wrong_registration_still_allows_exact_brand_for_mismatch_detection() -> None:
    result = _candidates(
        registration_number="ZZ-9999",
        brand_name="Acimox Capsule",
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].matched_by == "brand_name_exact"
    assert result.exact_registration_product_id is None
    assert result.fuzzy_suggestions_used is False


def test_exact_generic_name_returns_every_product() -> None:
    result = _candidates(generic_name="Paracetamol")

    assert len(result.candidates) == 2
    assert {item.product.registration_number for item in result.candidates} == {
        "A11-0131", "A4-0704",
    }
    assert all(item.matched_by == "generic_name_exact" for item in result.candidates)
    assert all(item.requires_confirmation for item in result.candidates)
    assert result.requires_confirmation is True


def test_generic_name_in_single_sms_name_field_also_preserves_all_products() -> None:
    result = _candidates(brand_name="Paracetamol")

    assert len(result.candidates) == 2
    assert all(item.matched_by == "generic_name_exact" for item in result.candidates)


def test_fuzzy_candidates_are_suggestions_with_similarity_scores_only() -> None:
    result = _candidates(brand_name="Ablept 300 Capusles")

    assert result.fuzzy_suggestions_used is True
    assert result.candidates
    top = result.candidates[0]
    assert top.matched_by == "fuzzy_brand_name"
    assert top.product.brand_name == "Ablept 300 Capsules"
    assert top.similarity_score is not None and top.similarity_score >= 72
    assert top.requires_confirmation is True
    assert "similarity_score" in top.model_dump()
    assert "confidence" not in top.model_dump()
    assert "probability" not in top.model_dump()


def test_duplicate_retrieval_paths_are_merged_for_one_product() -> None:
    result = _candidates(
        registration_number="A4-8982",
        brand_name="Acimox Capsule",
    )

    assert len(result.candidates) == 1
    paths = set(result.candidates[0].matched_paths)
    assert paths == {"registration_number_exact", "brand_name_exact"}
    assert result.candidates[0].requires_confirmation is False
