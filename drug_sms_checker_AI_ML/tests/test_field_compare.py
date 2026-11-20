"""Field-level comparison tests for all seven required fields."""

from __future__ import annotations

from src.catalogue import load_catalogue
from src.field_compare import FieldComparison, compare_fields, comparisons_by_field
from src.observation import MedicineObservation, ObservedField

CATALOGUE = load_catalogue()
AZITHRO = CATALOGUE.registration_lookup("B4-1180")
PREGABALIN = CATALOGUE.registration_lookup("A4-101466")
DEXTROSE = CATALOGUE.registration_lookup("04-0858")

assert AZITHRO is not None
assert PREGABALIN is not None
assert DEXTROSE is not None


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
    adapted = {
        name: value if isinstance(value, ObservedField) else ObservedField.present(value, f"test.{name}")
        for name, value in values.items()
    }
    return MedicineObservation(observation_id="TEST", source_channel="sms", **adapted)


def _statuses(observation: MedicineObservation, product) -> dict[str, FieldComparison]:
    return comparisons_by_field(compare_fields(observation, product))


def test_all_seven_fields_are_compared_in_stable_order() -> None:
    rows = compare_fields(_observation(), AZITHRO)

    assert [row.field for row in rows] == [
        "registration_number",
        "brand_name",
        "generic_name",
        "manufacturer",
        "strength",
        "dosage_form",
        "package_volume",
    ]
    assert {row.status for row in rows} == {"UNKNOWN"}


def test_registration_number_is_exact_only() -> None:
    match = _statuses(_observation(registration_number="b4‐1180"), AZITHRO)
    mismatch = _statuses(_observation(registration_number="B4-1181"), AZITHRO)

    assert match["registration_number"].status == "MATCH"
    assert mismatch["registration_number"].status == "MISMATCH"
    assert "never fuzzy-matched" in mismatch["registration_number"].reason


def test_brand_mismatch_keeps_similarity_score_separate() -> None:
    rows = _statuses(
        _observation(brand_name="1980 Azithromycin USP 500 mg Tablets"),
        AZITHRO,
    )
    brand = rows["brand_name"]

    assert brand.status == "MISMATCH"
    assert brand.similarity_score is not None
    assert "supporting evidence only" in brand.reason
    assert "confidence" not in brand.model_dump()


def test_generic_name_and_manufacturer_compare_only_when_present() -> None:
    good = _statuses(
        _observation(
            generic_name="Azithromycin (Azithromycin Dihydrate)",
            manufacturer="Surmount Laboratories Pvt Ltd",
        ),
        AZITHRO,
    )
    bad_manufacturer = _statuses(
        _observation(manufacturer="Different Pharma Ltd"),
        AZITHRO,
    )
    missing_catalogue_manufacturer = _statuses(
        _observation(manufacturer="1980 Pharmaceutical Limited"),
        PREGABALIN,
    )

    assert good["generic_name"].status == "MATCH"
    assert good["manufacturer"].status == "MATCH"
    assert bad_manufacturer["manufacturer"].status == "MISMATCH"
    assert missing_catalogue_manufacturer["manufacturer"].status == "UNKNOWN"
    assert "applicant_name is never used" in missing_catalogue_manufacturer["manufacturer"].reason


def test_strength_values_are_parsed_with_units() -> None:
    same = _statuses(_observation(strength="250 mg"), AZITHRO)
    different = _statuses(_observation(strength="500 mg"), AZITHRO)
    volume_as_strength = _statuses(_observation(strength="100 ml"), AZITHRO)

    assert same["strength"].status == "MATCH"
    assert different["strength"].status == "MISMATCH"
    assert volume_as_strength["strength"].status == "UNPARSED"
    assert volume_as_strength["strength"].status != "MATCH"
    assert "package volume cannot be used as strength" in volume_as_strength["strength"].reason


def test_dosage_form_and_package_volume_are_separate_fields() -> None:
    rows = _statuses(
        _observation(
            brand_name="10% Dextrose (500/1000 mL)",
            strength="10 %",
            package_volume="1000 ml",
        ),
        DEXTROSE,
    )

    assert rows["package_volume"].status == "MATCH"
    assert rows["strength"].status == "MATCH"
    assert rows["dosage_form"].status == "UNKNOWN"
    assert rows["package_volume"].catalogue_normalized == "1000 ml"
    assert rows["strength"].catalogue_normalized == "10 %"


def test_observation_conflict_propagates_with_original_values() -> None:
    conflict = ObservedField.conflict(
        "Bode Sudrex (Headache & Fever)",
        "Bode Sudrex (Headache & Fever; Two-Layer Tablets)",
        "test.conflict",
    )
    rows = _statuses(_observation(brand_name=conflict), AZITHRO)

    assert rows["brand_name"].status == "CONFLICT"
    assert "||" in (rows["brand_name"].observed_raw or "")
    assert rows["brand_name"].observed_normalized is None
