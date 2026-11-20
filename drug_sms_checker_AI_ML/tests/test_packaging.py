"""Offline dataset-integrity and multi-image reconciliation tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.packaging import (
    STATUS_CONFLICT,
    STATUS_CONSISTENT,
    STATUS_DAYLIGHT_ONLY,
    STATUS_INDOOR_ONLY,
    STATUS_NOT_VISIBLE,
    classify_pair,
    read_csv_rows,
    reconcile_medicine,
    reconcile_packaging,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "data" / "packaging"
OCR = PACKAGING / "ocr_results.csv"
RESULTS = PACKAGING / "package_results.csv"
FOLDERS = {
    "daylight": PACKAGING / "daylight",
    "indoor": PACKAGING / "indoor",
}


def _rows(path: Path) -> list[dict[str, str]]:
    return read_csv_rows(path)


def test_dataset_shape_and_filename_validation() -> None:
    rows = _rows(OCR)
    ids = [r["medicine_id"] for r in rows]

    assert len(rows) == 22
    assert len(set(ids)) == 11
    assert set(ids) == {f"pack_{i:02d}" for i in range(1, 12)}

    for medicine_id in set(ids):
        pairs = [r for r in rows if r["medicine_id"] == medicine_id]
        assert len(pairs) == 2
        assert {r["image_condition"] for r in pairs} == {"daylight", "indoor"}

    for condition, folder in FOLDERS.items():
        actual = {p.name for p in folder.iterdir() if p.is_file()}
        assert len(actual) == 11
        recorded = [r["image_filename"] for r in rows if r["image_condition"] == condition]
        assert len(recorded) == 11
        assert set(recorded) == actual
        for filename in recorded:
            assert (folder / filename).is_file()


def test_duplicate_records_are_rejected() -> None:
    rows = _rows(OCR)
    with pytest.raises(ValueError, match="duplicate daylight record"):
        reconcile_packaging(rows + [dict(rows[0])])


def test_missing_image_condition_is_rejected() -> None:
    rows = [r for r in _rows(OCR) if not (
        r["medicine_id"] == "pack_01" and r["image_condition"] == "indoor"
    )]
    with pytest.raises(ValueError, match="missing indoor record"):
        reconcile_packaging(rows)


def test_generated_package_results_matches_reconciliation() -> None:
    expected = reconcile_packaging(_rows(OCR))
    actual = _rows(RESULTS)

    assert [r["medicine_id"] for r in expected] == [r["medicine_id"] for r in actual]
    for want, got in zip(expected, actual):
        assert got == want


def test_both_images_agree() -> None:
    result = classify_pair("brand_name", "Test Brand", "TEST  BRAND")
    assert result["status"] == STATUS_CONSISTENT
    assert result["value"] == "Test Brand"


def test_daylight_only_and_indoor_only_are_not_conflicts() -> None:
    day = classify_pair("registration_number", "04-1234", "Not visible")
    indoor = classify_pair("manufacturer", "Not visible", "Example Pharma Ltd")

    assert day["status"] == STATUS_DAYLIGHT_ONLY
    assert day["value"] == "04-1234"
    assert indoor["status"] == STATUS_INDOOR_ONLY
    assert indoor["value"] == "Example Pharma Ltd"


def test_both_images_unreadable() -> None:
    result = classify_pair("strength", "Not visible", "")
    assert result["status"] == STATUS_NOT_VISIBLE
    assert result["value"] == "not visible"


@pytest.mark.parametrize(
    ("field", "daylight", "indoor"),
    [
        ("registration_number", "04-1111", "04-2222"),
        ("manufacturer", "Alpha Pharma", "Beta Pharma"),
        ("brand_name", "Product A (Tablets)", "Product B (Tablets)"),
        ("strength", "100 mg", "200 mg"),
    ],
)
def test_different_readable_values_are_conflicts(field: str, daylight: str, indoor: str) -> None:
    result = classify_pair(field, daylight, indoor)
    assert result["status"] == STATUS_CONFLICT
    assert result["daylight_raw"] == daylight
    assert result["indoor_raw"] == indoor


def test_brand_punctuation_difference_is_not_a_conflict() -> None:
    result = classify_pair("brand_name", "Test-Brand (10 ml)", "test brand 10 ml")
    assert result["status"] == STATUS_CONSISTENT
    assert result["value"] == "Test-Brand (10 ml)"


def test_package_volume_is_not_treated_as_strength() -> None:
    day = {
        "medicine_id": "synthetic",
        "image_condition": "daylight",
        "brand_name": "Synthetic",
        "nafdac_registration_number": "Not visible",
        "manufacturer": "Not visible",
        "strength": "Not visible",
        "package_volume_separate_from_strength": "100 ml",
    }
    indoor = dict(day, image_condition="indoor")
    row = reconcile_medicine("synthetic", day, indoor)

    assert row["strength_status"] == STATUS_NOT_VISIBLE
    assert row["strength"] == "not visible"
    assert row["package_volume"] == "100 ml"
    assert row["package_volume_status"] == STATUS_CONSISTENT
    assert row["package_volume_not_strength"] == "100 ml"


def test_known_pack_classifications_and_manual_review_flags() -> None:
    rows = {r["medicine_id"]: r for r in _rows(RESULTS)}

    assert rows["pack_05"]["manufacturer_status"] == STATUS_INDOOR_ONLY
    assert rows["pack_05"]["manual_review_required"] == "false"
    assert rows["pack_06"]["package_volume_status"] == STATUS_INDOOR_ONLY
    assert rows["pack_06"]["manual_review_required"] == "false"

    pack_10 = rows["pack_10"]
    assert pack_10["brand_status"] == STATUS_CONFLICT
    assert pack_10["brand_conflict_daylight"] == (
        "Bode Sudrex (Headache & Fever — Paracetamol, Caffeine; Two-Layer Tablets)"
    )
    assert pack_10["brand_conflict_indoor"] == (
        "Bode Sudrex (Headache & Fever — Paracetamol, Caffeine)"
    )
    assert pack_10["registration_status"] == STATUS_DAYLIGHT_ONLY
    assert pack_10["manual_review_required"] == "true"
    assert pack_10["manual_review_fields"] == "brand_name"

    assert rows["pack_11"]["registration_status"] == STATUS_DAYLIGHT_ONLY
    assert rows["pack_11"]["manual_review_required"] == "false"


def test_only_genuine_conflicts_require_manual_review() -> None:
    rows = _rows(RESULTS)
    flagged = [r["medicine_id"] for r in rows if r["manual_review_required"] == "true"]
    assert flagged == ["pack_10"]

    status_columns = {
        "brand_name": "brand_status",
        "registration_number": "registration_status",
        "manufacturer": "manufacturer_status",
        "strength": "strength_status",
    }
    for row in rows:
        conflict_fields = [
            field for field, column in status_columns.items()
            if row[column] == STATUS_CONFLICT
        ]
        assert bool(conflict_fields) == (row["manual_review_required"] == "true")
        assert row["manual_review_fields"] == "; ".join(conflict_fields)
