"""Photo test harness and safety checks. Real-pack accuracy is NOT TESTED."""

import csv
from pathlib import Path

from src.photo import PhotoFields, PhotoResult, extract_photo_fields, validate_upload

TEMPLATE = Path(__file__).with_name("photo_test_template.csv")


def test_template_has_11_packs_in_two_lighting_conditions():
    with TEMPLATE.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 22
    assert len({r["pack_id"] for r in rows}) == 11
    assert {r["lighting"] for r in rows} == {"daylight", "indoor_tube_light"}
    assert all(r["result"] == "pending" for r in rows)
    assert all(not r["image_path"] for r in rows)


def test_no_real_pack_photos_means_accuracy_not_tested():
    result = extract_photo_fields(b"fake-image-bytes", "image/png", client=None)
    assert isinstance(result, PhotoResult)
    assert result.status == "NOT TESTED"
    assert result.accuracy_tested is False
    assert result.fields == PhotoFields()
    assert all(v == "not visible" for v in result.fields.model_dump().values())


def test_upload_validation():
    assert validate_upload("image/jpeg", 1024) is None
    assert validate_upload("image/png", 1024) is None
    assert validate_upload("image/webp", 1024) is None
    assert "Unsupported" in validate_upload("application/pdf", 1024)
    assert "empty" in validate_upload("image/png", 0)
    assert "larger" in validate_upload("image/png", 6 * 1024 * 1024)


def test_rejected_upload_never_runs_ocr():
    result = extract_photo_fields(b"PDFDATA", "application/pdf", client=None)
    assert result.status == "rejected"
    assert result.fields.registration_number == "not visible"
