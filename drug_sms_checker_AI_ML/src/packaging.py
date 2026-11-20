"""Deterministic package-photo reconciliation and ground-truth safety helpers.

This module reads the preserved image-level OCR records and produces one
consolidated record per medicine. It never calls Gemini, never invents a fact and
never treats a consolidated or Gemini-produced value as ground truth.

The canonical missing value is ``photo.NOT_VISIBLE`` (lowercase). Raw text in
``ocr_results.csv`` is preserved in its own columns; consolidation uses a
normalised comparison key only.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Mapping

from .photo import NOT_VISIBLE, is_missing

STATUS_CONSISTENT = "CONSISTENT"
STATUS_DAYLIGHT_ONLY = "DAYLIGHT_ONLY"
STATUS_INDOOR_ONLY = "INDOOR_ONLY"
STATUS_NOT_VISIBLE = "NOT_VISIBLE"
STATUS_CONFLICT = "CONFLICT"
CONFLICT_MARKER = "CONFLICT"

PRIMARY_FIELDS = ("brand_name", "registration_number", "manufacturer", "strength")
GROUND_TRUTH_FIELDS = PRIMARY_FIELDS

_OCR_COLUMNS: dict[str, str] = {
    "brand_name": "brand_name",
    "registration_number": "nafdac_registration_number",
    "manufacturer": "manufacturer",
    "strength": "strength",
    "package_volume": "package_volume_separate_from_strength",
}

PACKAGE_RESULT_FIELDS = (
    "medicine_id",
    "brand_name",
    "brand_comparison",
    "brand_source",
    "nafdac_registration_number",
    "registration_comparison",
    "registration_source",
    "manufacturer",
    "manufacturer_comparison",
    "manufacturer_source",
    "strength",
    "strength_comparison",
    "strength_source",
    "package_volume_not_strength",
    "package_volume_comparison",
    "manual_review_required",
    "manual_review_fields",
    "notes",
    "brand_status",
    "brand_conflict_daylight",
    "brand_conflict_indoor",
    "registration_status",
    "registration_conflict_daylight",
    "registration_conflict_indoor",
    "manufacturer_status",
    "manufacturer_conflict_daylight",
    "manufacturer_conflict_indoor",
    "strength_status",
    "strength_conflict_daylight",
    "strength_conflict_indoor",
    "package_volume",
    "package_volume_status",
    "package_volume_daylight",
    "package_volume_indoor",
    "package_volume_discrepancy",
)


def read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    """Read a UTF-8 CSV into plain string rows."""
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_csv_rows(path: str | Path, rows: Iterable[Mapping[str, Any]],
                   fieldnames: Iterable[str] = PACKAGE_RESULT_FIELDS) -> None:
    """Write rows deterministically using the declared schema."""
    names = list(fieldnames)
    with Path(path).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=names, extrasaction="raise")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in names})


def _value(row: Mapping[str, Any], field: str) -> str:
    """Return the raw image-level text for a logical field."""
    return str(row.get(_OCR_COLUMNS[field], "") or "")


def comparison_key(field: str, value: str | None) -> str:
    """Build a conservative comparison key for an extracted value.

    Brand and manufacturer ignore harmless case/whitespace/punctuation changes.
    Registration numbers keep their hyphen because it is part of the real NRN.
    Strength and volume keep punctuation because units and separators matter.
    """
    if is_missing(value):
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip()
    text = re.sub(r"\s+", " ", text)
    if field == "registration_number":
        return re.sub(r"[-‐‑‒–—―]", "-", text, flags=re.UNICODE).upper()
    if field in {"brand_name", "manufacturer"}:
        # Replace punctuation with a boundary instead of deleting it:
        # "Test-Brand" and "Test Brand" must compare equal.
        text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
        return re.sub(r"\s+", " ", text).strip().casefold()
    return text.casefold()


def classify_pair(field: str, daylight_raw: str | None,
                  indoor_raw: str | None) -> dict[str, Any]:
    """Apply the exact daylight/indoor reconciliation rules to one field."""
    day = str(daylight_raw or "")
    indoor = str(indoor_raw or "")
    day_missing = is_missing(day)
    indoor_missing = is_missing(indoor)
    day_key = comparison_key(field, day)
    indoor_key = comparison_key(field, indoor)

    if day_missing and indoor_missing:
        status, value, source = STATUS_NOT_VISIBLE, NOT_VISIBLE, "Neither"
    elif day_missing:
        status, value, source = STATUS_INDOOR_ONLY, indoor, "Indoor"
    elif indoor_missing:
        status, value, source = STATUS_DAYLIGHT_ONLY, day, "Daylight"
    elif day_key == indoor_key:
        status, value, source = STATUS_CONSISTENT, day, "Daylight + Indoor"
    else:
        status, value, source = STATUS_CONFLICT, CONFLICT_MARKER, "CONFLICT"

    return {
        "status": status,
        "value": value,
        "source": source,
        "daylight_raw": day,
        "indoor_raw": indoor,
        "conflict": status == STATUS_CONFLICT,
    }


def _pill(prefix: str, result: Mapping[str, Any]) -> dict[str, Any]:
    """Flatten a field result into the legacy and explicit output columns."""
    return {
        f"{prefix}_comparison": result["status"],
        f"{prefix}_source": result["source"],
        f"{prefix}_status": result["status"],
        f"{prefix}_conflict_daylight": result["daylight_raw"] if result["conflict"] else "",
        f"{prefix}_conflict_indoor": result["indoor_raw"] if result["conflict"] else "",
    }


def reconcile_medicine(medicine_id: str, daylight: Mapping[str, Any],
                       indoor: Mapping[str, Any]) -> dict[str, Any]:
    """Consolidate two image-level records into one medicine-level row."""
    fields = {name: classify_pair(name, _value(daylight, name), _value(indoor, name))
              for name in PRIMARY_FIELDS}
    volume = classify_pair("package_volume",
                           _value(daylight, "package_volume"),
                           _value(indoor, "package_volume"))

    review_fields = [name for name in PRIMARY_FIELDS if fields[name]["conflict"]]

    row: dict[str, Any] = {
        "medicine_id": medicine_id,
        "brand_name": fields["brand_name"]["value"],
        "nafdac_registration_number": fields["registration_number"]["value"],
        "manufacturer": fields["manufacturer"]["value"],
        "strength": fields["strength"]["value"],
        "package_volume_not_strength": volume["value"],
        "package_volume": volume["value"],
        "manual_review_required": str(bool(review_fields)).lower(),
        "manual_review_fields": "; ".join(review_fields),
        "notes": "One or more extracted values require manual review." if review_fields else "",
        "package_volume_daylight": volume["daylight_raw"],
        "package_volume_indoor": volume["indoor_raw"],
        "package_volume_discrepancy": str(
            volume["status"] not in {STATUS_CONSISTENT, STATUS_NOT_VISIBLE}
        ).lower(),
    }
    row.update(_pill("brand", fields["brand_name"]))
    row.update(_pill("registration", fields["registration_number"]))
    row.update(_pill("manufacturer", fields["manufacturer"]))
    row.update(_pill("strength", fields["strength"]))
    row["package_volume_comparison"] = volume["status"]
    row["package_volume_status"] = volume["status"]
    return row


def reconcile_packaging(ocr_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Reconcile all image-level OCR rows, grouped by medicine ID."""
    grouped: dict[str, dict[str, Mapping[str, Any]]] = {}
    order: list[str] = []
    for row in ocr_rows:
        medicine_id = str(row.get("medicine_id", "") or "").strip()
        condition = str(row.get("image_condition", "") or "").strip().casefold()
        if not medicine_id:
            raise ValueError("image-level row has no medicine_id")
        if condition not in {"daylight", "indoor"}:
            raise ValueError(f"{medicine_id}: unknown image_condition {condition!r}")
        if medicine_id not in grouped:
            grouped[medicine_id] = {}
            order.append(medicine_id)
        if condition in grouped[medicine_id]:
            raise ValueError(f"{medicine_id}: duplicate {condition} record")
        grouped[medicine_id][condition] = row

    results: list[dict[str, Any]] = []
    for medicine_id in order:
        pair = grouped[medicine_id]
        if set(pair) != {"daylight", "indoor"}:
            missing = sorted({"daylight", "indoor"} - set(pair))
            raise ValueError(f"{medicine_id}: missing {', '.join(missing)} record")
        results.append(reconcile_medicine(medicine_id, pair["daylight"], pair["indoor"]))
    return results


def _observed_value(row: Mapping[str, Any], field: str) -> str:
    key = "nafdac_registration_number" if field == "registration_number" else field
    return str(row.get(key, "") or "")


def evaluate_ground_truth(ground_truth_rows: Iterable[Mapping[str, Any]],
                          observed_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Score only fields with independently verified ground truth.

    If no ground-truth field is populated, the result is explicitly NOT TESTED
    and carries no accuracy percentage. Observed/Gemini values are used only as
    candidates on the right-hand side of a comparison, never as the expected
    value.
    """
    observed_by_id = {str(r.get("medicine_id", "") or "").strip(): r for r in observed_rows}
    scored: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for gt in ground_truth_rows:
        medicine_id = str(gt.get("medicine_id", "") or "").strip()
        for field in GROUND_TRUTH_FIELDS:
            expected = str(gt.get(field, "") or "")
            if is_missing(expected):
                skipped.append({"medicine_id": medicine_id, "field": field,
                                "reason": "ground_truth_missing"})
                continue
            observed = observed_by_id.get(medicine_id)
            if observed is None:
                skipped.append({"medicine_id": medicine_id, "field": field,
                                "reason": "observed_record_missing"})
                continue
            actual = _observed_value(observed, field)
            if is_missing(actual):
                skipped.append({"medicine_id": medicine_id, "field": field,
                                "reason": "observed_value_missing"})
                continue
            correct = comparison_key(field, expected) == comparison_key(field, actual)
            scored.append({"medicine_id": medicine_id, "field": field,
                           "correct": correct})

    count = len(scored)
    correct_count = sum(item["correct"] for item in scored)
    accuracy = (correct_count / count) if count else None
    return {
        "status": "NOT TESTED" if not count else "SCORABLE_FIELDS_AVAILABLE",
        "accuracy_tested": bool(count),
        "scored_fields": count,
        "skipped_fields": len(skipped),
        "correct_fields": correct_count if count else None,
        "accuracy": accuracy,
        "accuracy_percent": round(accuracy * 100, 1) if accuracy is not None else None,
        "skipped": skipped,
        "explanation": (
            "No independently verified ground-truth field is populated; "
            "accuracy is NOT TESTED. Gemini/consolidated outputs must never be used as ground truth."
            if not count else
            "Only populated ground-truth fields were scored; missing fields were excluded."
        ),
    }
