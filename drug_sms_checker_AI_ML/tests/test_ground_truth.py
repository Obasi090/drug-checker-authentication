"""Ground-truth protection tests: empty verification data must stay NOT TESTED."""

from __future__ import annotations

from pathlib import Path

from src.packaging import evaluate_ground_truth, read_csv_rows

ROOT = Path(__file__).resolve().parents[1]
PACKAGING = ROOT / "data" / "packaging"


def test_empty_ground_truth_does_not_generate_accuracy_claims() -> None:
    ground_truth = read_csv_rows(PACKAGING / "ground_truth.csv")
    observed = read_csv_rows(PACKAGING / "package_results.csv")

    report = evaluate_ground_truth(ground_truth, observed)

    assert report["status"] == "NOT TESTED"
    assert report["accuracy_tested"] is False
    assert report["scored_fields"] == 0
    assert report["accuracy"] is None
    assert report["accuracy_percent"] is None
    assert "NOT TESTED" in report["explanation"]


def test_missing_fields_are_excluded_from_scoring() -> None:
    # Synthetic fixture only: these are not real medicine facts.
    ground_truth = [{
        "medicine_id": "synthetic_1",
        "brand_name": "Synthetic Brand",
        "registration_number": "",
        "manufacturer": "Not visible",
        "strength": "",
    }]
    observed = [{
        "medicine_id": "synthetic_1",
        "brand_name": "Synthetic Brand",
        "nafdac_registration_number": "ZZ-0001",
        "manufacturer": "Synthetic Maker",
        "strength": "10 mg",
    }]

    report = evaluate_ground_truth(ground_truth, observed)

    assert report["accuracy_tested"] is True
    assert report["scored_fields"] == 1
    assert report["skipped_fields"] == 3
    assert report["correct_fields"] == 1
    assert report["accuracy"] == 1.0
    assert {item["reason"] for item in report["skipped"]} == {"ground_truth_missing"}


def test_gemini_outputs_are_never_treated_as_ground_truth() -> None:
    ground_truth = [{
        "medicine_id": "synthetic_2",
        "brand_name": "",
        "registration_number": "",
        "manufacturer": "",
        "strength": "",
    }]
    observed = [{
        "medicine_id": "synthetic_2",
        "brand_name": "Gemini Guessed Brand",
        "nafdac_registration_number": "ZZ-9999",
        "manufacturer": "Gemini Guessed Maker",
        "strength": "999 mg",
    }]

    report = evaluate_ground_truth(ground_truth, observed)

    assert report["accuracy_tested"] is False
    assert report["scored_fields"] == 0
    assert report["accuracy"] is None
    assert "never be used as ground truth" in report["explanation"].lower()
