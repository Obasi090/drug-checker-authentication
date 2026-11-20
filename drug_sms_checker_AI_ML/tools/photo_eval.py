"""Read-only evaluation workflow for the 11-pack photo test template.

Real packaging images exist under ``data/packaging/``, but the independent
verification fields in ``ground_truth.csv`` are empty, so the default output is
explicitly ``REAL-PACK OCR ACCURACY: NOT TESTED``. Fill the template from
independently verified packaging, then rerun this script.

Usage:  python tools/photo_eval.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.packaging import evaluate_ground_truth, read_csv_rows  # noqa: E402

TEMPLATE = ROOT / "tests" / "photo_test_template.csv"
GROUND_TRUTH = ROOT / "data" / "packaging" / "ground_truth.csv"
PACKAGE_RESULTS = ROOT / "data" / "packaging" / "package_results.csv"
VALID_RESULTS = {"correct", "incorrect", "not_visible"}


def main() -> None:
    with TEMPLATE.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))

    packs = {r["pack_id"] for r in rows}
    lightings = {r["lighting"] for r in rows}
    print(f"template: {TEMPLATE.name}")
    print(f"captures: {len(rows)} | packs: {len(packs)} | lighting: {sorted(lightings)}")

    report = evaluate_ground_truth(
        read_csv_rows(GROUND_TRUTH), read_csv_rows(PACKAGE_RESULTS)
    )
    print(f"ground truth: {report['status']}")
    print(f"verified fields: {report['scored_fields']} | excluded fields: {report['skipped_fields']}")
    if not report["accuracy_tested"]:
        print("REAL-PACK OCR ACCURACY: NOT TESTED")
        print("reason: no independently verified ground-truth field is populated;")
        print("        Gemini/consolidated outputs must never be used as ground truth.")
        return

    incomplete = [
        r for r in rows
        if not r["image_path"] or r["result"] == "pending" or r["result"] not in VALID_RESULTS
    ]
    if incomplete:
        print("REAL-PACK OCR ACCURACY: NOT TESTED")
        print(f"incomplete captures: {len(incomplete)} of {len(rows)}")
        print("next: fill image_path, expected/observed registration number and result.")
        return

    correct = sum(r["result"] == "correct" for r in rows)
    accuracy = correct / len(rows)
    print(f"exact registration-number accuracy: {correct}/{len(rows)} = {accuracy:.1%}")
    if accuracy < 0.70:
        print("RECOMMENDATION: exclude live OCR from the demo; show recording/roadmap instead.")
    else:
        print("RECOMMENDATION: still show extracted fields for user edit/confirmation before lookup.")


if __name__ == "__main__":
    main()
