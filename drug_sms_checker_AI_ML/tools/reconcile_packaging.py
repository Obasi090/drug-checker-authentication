"""Regenerate package_results.csv from the preserved image-level OCR records.

Usage:  python tools/reconcile_packaging.py

This is a deterministic, offline transformation. It never calls Gemini and
never writes to ground_truth.csv or to the source images.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.packaging import read_csv_rows, reconcile_packaging, write_csv_rows  # noqa: E402

OCR = ROOT / "data" / "packaging" / "ocr_results.csv"
OUTPUT = ROOT / "data" / "packaging" / "package_results.csv"


def main() -> None:
    rows = reconcile_packaging(read_csv_rows(OCR))
    write_csv_rows(OUTPUT, rows)
    reviews = [r["medicine_id"] for r in rows if r["manual_review_required"] == "true"]
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
    print(f"medicines: {len(rows)} | manual review: {reviews or 'none'}")


if __name__ == "__main__":
    main()
