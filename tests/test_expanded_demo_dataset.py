from __future__ import annotations

import json
from pathlib import Path


DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "greenbook_sample.json"
DEMO_NOTE_PREFIX = "DEMO/SAMPLE ONLY"


def test_sample_dataset_retains_originals_and_has_60_explicit_demo_records():
    records = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    assert len(records) == 80
    synthetic = [
        record for record in records
        if str(record.get("dataQualityNote") or "").startswith(DEMO_NOTE_PREFIX)
    ]
    originals = [record for record in records if record not in synthetic]

    assert len(synthetic) == 60
    assert len(originals) == 20
    assert all(record["productId"] < 99000021 for record in originals)
    assert len({record["productId"] for record in records}) == 80
    assert len({record["registrationNumber"] for record in records}) == 80

    for record in synthetic:
        assert record["registrationNumber"].startswith("DMO-")
        assert "DEMO/SAMPLE" in record["productName"]
        assert "DEMO/SAMPLE" in record["status"]
        assert record["manufacturer"] is None
        assert record["applicant"] is None
        assert record["approvedAt"] is None
        assert record["expiresAt"] is None
        assert record["detailUrl"] is None
        assert record["sourceUrl"] is None
        assert record["fetchedAt"] is None
