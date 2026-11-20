from __future__ import annotations

import sqlite3
from io import BytesIO
from types import SimpleNamespace

import pytest

from drug_checker import api
from drug_checker.db_ops import upsert_drug
from drug_checker.db_setup import create_all_tables


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "api-test.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    assert create_all_tables(conn)
    upsert_drug(conn, {
        "product_id": 901,
        "reg_number": "T4-9012",
        "brand_name": "API Fixture Medicine",
        "generic_name": "Shared fixture ingredient",
        "registry_status": "Active",
    })
    upsert_drug(conn, {
        "product_id": 902,
        "reg_number": "T4-9013",
        "brand_name": "API Fixture Medicine Two",
        "generic_name": "Shared fixture ingredient",
        "registry_status": "Active",
    })
    conn.close()
    def open_test_db(_path):
        connection = sqlite3.connect(db_path)
        connection.row_factory = sqlite3.Row
        return connection

    monkeypatch.setattr(api, "create_connection", open_test_db)
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("AI_ML_MOCK", "1")
    app = api.create_app()
    app.config.update(TESTING=True, TEST_DB_PATH=db_path)
    return app.test_client()


def test_api_lookup_by_name_and_registration(client):
    by_name = client.post("/api/check", json={"message": "API Fixture Medicine"})
    by_reg = client.post("/api/check", json={"message": "T4-9012"})
    assert by_name.status_code == 200
    assert by_name.json["findings"]["status"] == "found"
    assert by_reg.status_code == 200
    assert by_reg.json["findings"]["matches"][0]["reg_number"] == "T4-9012"


def test_api_input_errors_are_json(client):
    assert client.post("/api/check", json={}).status_code == 400
    assert client.post("/api/check", json={"message": ""}).status_code == 200
    assert client.post("/api/check", data="{", content_type="application/json").status_code == 400
    assert client.post("/api/check", data="message=x", content_type="text/plain").status_code == 400
    response = client.post("/api/check", json={"message": 42})
    assert response.status_code == 400
    assert response.is_json and "error" in response.json


def test_api_packet_comparison_is_not_pack_authentication(client):
    response = client.post("/api/check-packet", json={
        "reg_number": "T4-9012",
        "brand_name": "Different visible name",
    })
    assert response.status_code == 200
    assert response.json["findings"]["status"] == "found"
    assert any(
        mismatch["field"] == "brand_name"
        for mismatch in response.json["findings"]["mismatches"]
    )
    assert "genuine" not in str(response.json).casefold()
    assert "authentic" not in str(response.json).casefold()


def test_database_error_returns_generic_response(client, monkeypatch):
    class FailingConnection:
        def execute(self, *_args, **_kwargs):
            raise sqlite3.OperationalError("private database detail")

        def close(self):
            pass

    monkeypatch.setattr(api, "create_connection", lambda _path: FailingConnection())
    response = client.get("/api/health")
    assert response.status_code == 500
    assert "private database detail" not in response.get_data(as_text=True)


def test_text_fallback_does_not_attempt_missing_parser(client, caplog):
    with caplog.at_level("ERROR", logger="drug_checker.engine"):
        response = client.post("/api/check", json={"message": "API Fixture Medicine"})
    assert response.status_code == 200
    assert "Could not import message parser" not in caplog.text


def test_not_found_sms_reports_unknown_alert_dataset(client):
    response = client.post("/api/check", json={"message": "unknown synthetic query"})
    assert response.status_code == 200
    reply = response.json["sms_reply"].casefold()
    assert "not found does not mean" in reply or "does not mean" in reply
    assert "alert data" in reply and "unknown" in reply
    assert "no alert matched" not in reply


def test_api_multiple_candidates_are_preserved(client):
    response = client.post("/api/check", json={"message": "Shared fixture ingredient"})
    assert response.status_code == 200
    assert response.json["findings"]["status"] == "multiple"
    assert len(response.json["findings"]["matches"]) == 2
    assert "unknown" in response.json["sms_reply"].casefold()
    assert len(response.json["sms_reply"]) <= 160


def test_health_exposes_unknown_dataset_states(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json["registry_data_status"]["status"] == "unknown"
    assert response.json["alert_data_status"]["status"] == "unknown"


def test_informal_message_uses_ai_parser_then_backend(client):
    response = client.post("/api/check", json={"message": "abeg check API Fixture Medicine for me"})
    assert response.status_code == 200
    assert response.json["findings"]["status"] == "found"
    assert response.json["findings"]["matches"][0]["product_id"] == 901
    assert response.json["explanation"]["mode"] == "deterministic"
    assert response.json["explanation"]["text"]


def test_uncertain_message_parser_requests_clarification(client):
    response = client.post("/api/check", json={"message": "check please"})
    assert response.status_code == 200
    assert response.json["findings"]["status"] == "invalid"
    assert response.json["findings"]["reason"] == "clarification_required"


def test_optional_parser_missing_keeps_backend_available(client, monkeypatch):
    from drug_checker import ai_integration
    monkeypatch.setattr(ai_integration, "_load_message_parser", lambda: None)
    response = client.post("/api/check", json={"message": "API Fixture Medicine"})
    assert response.status_code == 200
    assert response.json["findings"]["status"] == "found"
    assert response.json["explanation"]["mode"] == "deterministic"


def test_optional_gemini_exact_extraction_is_validated_before_lookup(client, monkeypatch):
    from drug_checker import ai_integration

    class ParserIntent:
        medical_question = False
        needs_clarification = True
        intent = "clarify"
        registration_number = None
        name = None

    class FakeClient:
        available = True

        def extract_intent(self, _text):
            return SimpleNamespace(registration_number=None, name="API Fixture Medicine")

    monkeypatch.setattr(ai_integration, "_load_message_parser", lambda: lambda *_args: ParserIntent())
    monkeypatch.setattr(ai_integration, "_load_gemini_client", lambda: FakeClient())
    response = client.post("/api/check", json={"message": "please look up API Fixture Medicine"})
    assert response.json["findings"]["status"] == "found"

    class InventingClient(FakeClient):
        def extract_intent(self, _text):
            return SimpleNamespace(registration_number=None, name="Medicine never written")

    monkeypatch.setattr(ai_integration, "_load_gemini_client", lambda: InventingClient())
    response = client.post("/api/check", json={"message": "please look up API Fixture Medicine"})
    assert response.json["findings"]["status"] == "invalid"


def test_photo_extract_returns_unconfirmed_fields_and_rejects_bad_uploads(client, monkeypatch):
    from drug_checker import api
    captured = {}

    def fake_reader(image_bytes, mime_type):
        captured["size"] = len(image_bytes)
        captured["mime"] = mime_type
        return {
            "fields": {
                "brand_name": "OCR Fixture Name",
                "registration_number": "T4-9012",
                "manufacturer": "not visible",
                "strength": "10 mg",
            },
            "status": "ok",
            "accuracy_tested": False,
            "message": "Review and confirm these visible fields.",
            "confirmed": False,
        }

    monkeypatch.setattr(api, "extract_visible_fields", fake_reader)
    png = b"\x89PNG\r\n\x1a\n" + b"test-image-bytes"
    response = client.post(
        "/api/photo/extract",
        data={"image": (BytesIO(png), "pack.png", "image/png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.json["confirmed"] is False
    assert response.json["physical_authentication"] is False
    assert response.json["fields"]["brand_name"] == "OCR Fixture Name"
    assert captured == {"size": len(png), "mime": "image/png"}

    unsupported = client.post(
        "/api/photo/extract",
        data={"image": (BytesIO(b"%PDF"), "pack.pdf", "application/pdf")},
        content_type="multipart/form-data",
    )
    assert unsupported.status_code == 415
    mismatch = client.post(
        "/api/photo/extract",
        data={"image": (BytesIO(b"not-png"), "pack.png", "image/png")},
        content_type="multipart/form-data",
    )
    assert mismatch.status_code == 415
    oversized = client.post(
        "/api/photo/extract",
        data={"image": (BytesIO(png + b"x" * (5 * 1024 * 1024)), "pack.png", "image/png")},
        content_type="multipart/form-data",
    )
    assert oversized.status_code == 413


def test_photo_compare_requires_confirmation_and_uses_corrected_values(client):
    unconfirmed = client.post("/api/photo/compare", json={
        "confirmed": False,
        "fields": {"brand_name": "OCR Fixture Name", "registration_number": "T4-9012"},
    })
    assert unconfirmed.status_code == 400
    assert "confirm" in unconfirmed.json["error"].casefold()

    corrected = client.post("/api/photo/compare", json={
        "confirmed": True,
        "fields": {"brand_name": "API Fixture Medicine", "registration_number": "T4-9012"},
    })
    assert corrected.status_code == 200
    assert corrected.json["confirmed"] is True
    assert corrected.json["findings"]["status"] == "found"
    assert not any(item["field"] == "brand_name" for item in corrected.json["findings"]["mismatches"])


def test_photo_compare_rejects_conflicting_or_unconfirmed_data(client):
    response = client.post("/api/photo/compare", json={
        "confirmed": True,
        "fields": {"registration_number": "T4-9012", "reg_number": "T4-9999"},
    })
    assert response.status_code == 400
    response = client.post("/api/photo/compare", json={
        "confirmed": True,
        "fields": {"brand_name": "API Fixture Medicine", "unexpected": "value"},
    })
    assert response.status_code == 400


def test_gemini_explanation_cannot_mutate_backend_findings(client, monkeypatch):
    from drug_checker import ai_integration

    class MutatingClient:
        available = True

        def explain(self, _question, findings):
            findings.status = "not_found"
            return SimpleNamespace(
                reply="A bounded explanation based on backend findings.",
                used_fallback=False,
                used_mock=False,
                safety_action="",
            )

    monkeypatch.setattr(ai_integration, "_load_gemini_client", lambda: MutatingClient())
    response = client.post("/api/check", json={"message": "API Fixture Medicine"})
    assert response.status_code == 200
    assert response.json["findings"]["status"] == "found"
    assert response.json["explanation"]["mode"] == "gemini"


def test_explanation_dependency_failure_uses_deterministic_fallback(client, monkeypatch):
    from drug_checker import ai_integration
    original_import = ai_integration.importlib.import_module

    def without_optional_ai(name, *args, **kwargs):
        if name.startswith(ai_integration.AI_PACKAGE):
            raise ModuleNotFoundError("optional AI dependency unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(ai_integration.importlib, "import_module", without_optional_ai)
    response = client.post("/api/check", json={"message": "API Fixture Medicine"})
    assert response.status_code == 200
    assert response.json["findings"]["status"] == "found"
    assert response.json["explanation"]["mode"] == "deterministic"
    assert response.json["explanation"]["text"]


def test_synthetic_alert_is_identified_in_api_sms_and_explanation(client):
    from drug_checker.db_ops import add_alert
    db_path = client.application.config["TEST_DB_PATH"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    add_alert(conn, {
        "reg_number": "ZZ-0001",
        "product_name": "SYNTHETIC DEMO PRODUCT",
        "alert_type": "warning",
        "alert_date": "2026-01-01",
        "reason": "SYNTHETIC — DEMONSTRATION ONLY; not a real NAFDAC notice.",
        "source_link": "https://example.invalid/demo/synthetic-alert-v1",
        "source_kind": "synthetic",
    })
    conn.close()

    response = client.post("/api/check", json={"message": "ZZ-0001"})
    assert response.status_code == 200
    alert = response.json["findings"]["alerts"][0]
    assert alert["source_kind"] == "synthetic"
    assert alert["demo_label"] == "SYNTHETIC — DEMONSTRATION ONLY"
    assert "synthetic" in response.json["sms_reply"].casefold()
    assert "not a real nafdac notice" in response.json["sms_reply"].casefold()
    assert "synthetic" in response.json["explanation"]["text"].casefold()
    assert "not a real nafdac notice" in response.json["explanation"]["text"].casefold()
    assert response.json["findings"]["alert_data_status"]["status"] == "unknown"


def test_sample_scope_is_visible_in_health_lookup_sms_and_explanation(client):
    from datetime import datetime, timezone
    from drug_checker.db_ops import record_data_import
    db_path = client.application.config["TEST_DB_PATH"]
    conn = sqlite3.connect(db_path)
    now = datetime.now(timezone.utc).isoformat()
    record_data_import(
        conn, "registry", "NAFDAC Greenbook sample/demo dataset", now, 20,
        "success", completed_at=now, imported_count=20, updated_count=0,
        skipped_count=0, rejected_count=0, duplicate_count=0,
    )
    conn.close()

    health = client.get("/api/health")
    assert health.json["registry_scope"] == "sample_demo"
    response = client.post("/api/check", json={"message": "API Fixture Medicine"})
    assert response.json["findings"]["registry_scope"] == "sample_demo"
    assert "demo sample only" in response.json["sms_reply"].casefold()
    assert "demo sample" in response.json["explanation"]["text"].casefold()
