"""Local-only interactive tester for the frozen Drug SMS Checker AI/ML layer.

Start:  python tools/interactive_server.py
Open:   http://127.0.0.1:8765
Stop:   Ctrl+C in the terminal

This is a TEST HARNESS, separate from the core engine. It uses only the Python
standard library plus dependencies already declared in requirements.txt. It
binds to localhost only, has no backend dependency, and never prints or returns
a Gemini API key. Uploaded image bytes stay in memory and are never written.
"""

from __future__ import annotations

import base64
import binascii
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.gemini import GeminiClient  # noqa: E402
from src.observation import (  # noqa: E402
    OBSERVED_FIELDS,
    MedicineObservation,
    observation_from_sms_text,
)
from src.packaging import (  # noqa: E402
    classify_pair,
    read_csv_rows,
    reconcile_medicine,
)
from src.photo import NOT_VISIBLE, PhotoFields, extract_photo_fields  # noqa: E402
from src.verification import DEFAULT_PACKAGE_RESULTS, VerificationEngine  # noqa: E402
from tools.demo import build_sms_cases  # noqa: E402

HOST = "127.0.0.1"
PORT = 8765
MAX_BODY = 16 * 1024 * 1024
UI_FILE = Path(__file__).resolve().with_name("interactive_ui.html")

OCR_COLUMNS = {
    "brand_name": "brand_name",
    "registration_number": "nafdac_registration_number",
    "manufacturer": "manufacturer",
    "strength": "strength",
    "package_volume": "package_volume_separate_from_strength",
}

ENGINE = VerificationEngine()
_CLIENT: GeminiClient | None = None


def gemini_client() -> GeminiClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = GeminiClient()  # loads .env through the existing safe loader
    return _CLIENT


def observation_view(observation: MedicineObservation) -> dict[str, Any]:
    return {
        name: {
            "value": observation.field(name).value,
            "raw": observation.field(name).raw,
            "status": observation.field(name).status,
            "provenance": observation.field(name).provenance,
        }
        for name in OBSERVED_FIELDS
    }


def verification_view(result: Any) -> dict[str, Any]:
    names = {
        candidate.product.product_id: candidate.identity_label
        for candidate in result.candidates.candidates
    }
    candidates = [{
        "identity": candidate.identity_label,
        "product_id": candidate.product.product_id,
        "matched_by": candidate.matched_by,
        "matched_paths": candidate.matched_paths,
        "similarity_score": candidate.similarity_score,
        "requires_confirmation": candidate.requires_confirmation,
        "selected": candidate.product.product_id == result.selected_product_id,
        "reasons": candidate.reasons,
    } for candidate in result.candidates.candidates]
    comparisons = [{
        "candidate": names.get(product_id, product_id),
        "field": item.field,
        "status": item.status,
        "observed_raw": item.observed_raw,
        "catalogue_raw": item.catalogue_raw,
        "reason": item.reason,
        "similarity_score": item.similarity_score,
    } for product_id, rows in result.field_comparisons.items() for item in rows]
    return {
        "observation_id": result.observation_id,
        "source_channel": result.source_channel,
        "status": result.status,
        "status_explanation": result.status_explanation,
        "reasons": result.reasons,
        "selected_product_id": result.selected_product_id,
        "candidates": candidates,
        "field_comparisons": comparisons,
        "review_fields": result.review_fields,
        "missing_fields": result.missing_fields,
        "manual_review": result.is_manual_review,
        "accuracy_tested": result.accuracy_tested,
        "notes": result.notes,
    }


def sms_result(text: str, observation_id: str = "UI-SMS") -> dict[str, Any]:
    observation = observation_from_sms_text(
        text, ENGINE.catalogue.brand_names, observation_id=observation_id
    )
    result = ENGINE.verify(observation)
    view = verification_view(result)
    provenance = observation.provenance
    view["original"] = text
    view["observed"] = observation_view(observation)
    view["parsed"] = {
        "registration_number": provenance.get("original") and observation.field("registration_number").value,
        "name": observation.field("brand_name").value,
        "intent": provenance.get("intent"),
        "extracted_by": provenance.get("extracted_by"),
        "normalized": provenance.get("normalized"),
        "notes": provenance.get("parser_notes", []),
    }
    return view


def compare_fields_view(day_fields: dict[str, str], indoor_fields: dict[str, str],
                        medicine_id: str) -> dict[str, Any]:
    day_row = {column: str(day_fields.get(name, NOT_VISIBLE)) for name, column in OCR_COLUMNS.items()}
    indoor_row = {column: str(indoor_fields.get(name, NOT_VISIBLE)) for name, column in OCR_COLUMNS.items()}
    row = reconcile_medicine(medicine_id, day_row, indoor_row)
    details: list[dict[str, Any]] = []
    for name, column in OCR_COLUMNS.items():
        pair = classify_pair(name, day_row[column], indoor_row[column])
        details.append({
            "field": name,
            "status": pair["status"],
            "daylight_raw": pair["daylight_raw"],
            "indoor_raw": pair["indoor_raw"],
            "chosen_value": pair["value"],
            "source": pair["source"],
        })
    return {
        "medicine_id": medicine_id,
        "fields": details,
        "manual_review_required": row["manual_review_required"] == "true",
        "manual_review_fields": row["manual_review_fields"],
        "notes": row["notes"],
        "accuracy_tested": False,
    }


def dataset_medicine_ids() -> list[str]:
    return [row["medicine_id"] for row in read_csv_rows(DEFAULT_PACKAGE_RESULTS)]


def decode_upload(payload: dict[str, Any]) -> tuple[bytes, str]:
    data_url = str(payload.get("data_url", ""))
    if "," not in data_url:
        raise ValueError("Invalid image data URL")
    header, encoded = data_url.split(",", 1)
    mime = header.removeprefix("data:").split(";")[0] or "application/octet-stream"
    data = base64.b64decode(encoded, validate=True)
    return data, mime


class Handler(BaseHTTPRequestHandler):
    server_version = "DrugSMSCheckerTester/1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        print("  " + (fmt % args))

    def _send(self, payload: Any, status: int = 200, content_type: str = "application/json") -> None:
        if content_type.startswith("application/json"):
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        else:
            body = payload.encode("utf-8") if isinstance(payload, str) else payload
        self.send_response(status)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if "json" in content_type or "html" in content_type else ""))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        if length > MAX_BODY:
            raise ValueError("Request too large (maximum 16 MB)")
        raw = self.rfile.read(length)
        parsed = json.loads(raw.decode("utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Request body must be a JSON object")
        return parsed

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path in {"/", "/index.html"}:
                if not UI_FILE.is_file():
                    self._send({"error": "UI file missing"}, 500)
                    return
                self._send(UI_FILE.read_text(encoding="utf-8"), content_type="text/html")
                return
            if path == "/api/config":
                client = gemini_client()
                self._send({
                    "gemini_available": client.available,
                    "model": client.model,
                    "catalogue_rows": len(ENGINE.catalogue.products),
                    "medicine_ids": dataset_medicine_ids(),
                    "note": "API key is never displayed. Offline sections work without Gemini.",
                })
                return
            if path == "/api/catalogue":
                query = parse_qs(urlparse(self.path).query).get("q", [""])[0].strip().casefold()
                matches = []
                for product in ENGINE.catalogue.products:
                    haystack = " ".join(str(value or "") for value in (
                        product.brand_name, product.generic_name, product.registration_number,
                        product.applicant_name, product.manufacturer,
                    )).casefold()
                    if query and query not in haystack:
                        continue
                    matches.append({
                        "brand_name": product.brand_name,
                        "generic_name": product.generic_name,
                        "registration_number": product.registration_number,
                        "applicant_name": product.applicant_name,
                        "manufacturer": product.manufacturer,
                        "strength": product.derived_strength,
                        "dosage_forms": list(product.derived_dosage_forms),
                        "package_volume": product.derived_package_volume,
                    })
                self._send({"count": len(matches), "products": matches[:50],
                            "truncated": len(matches) > 50})
                return
            self._send({"error": "Not found"}, 404)
        except Exception as exc:
            self._send({"error": type(exc).__name__}, 500)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        started = time.perf_counter()
        try:
            payload = self._body()
            if path == "/api/sms":
                text = str(payload.get("text", ""))
                if not text.strip():
                    self._send({"error": "Enter a message first."}, 400)
                    return
                self._send(sms_result(text))
                return

            if path == "/api/photo":
                data, mime = decode_upload(payload)
                photo = extract_photo_fields(data, mime, gemini_client())
                fields = photo.fields.model_dump()
                verification = None
                if photo.status == "ok":
                    verification = verification_view(
                        ENGINE.verify_photo_result(photo, observation_id="UI-PHOTO")
                    )
                self._send({
                    "status": photo.status,
                    "message": photo.message,
                    "schema_validation": "VALID (PhotoFields, extra=forbid)" if photo.status == "ok" else "NOT APPLICABLE",
                    "gemini_available": gemini_client().available,
                    "fields": {**fields, "package_volume": NOT_VISIBLE},
                    "package_volume_note": "Package volume is not in the existing four-field extraction schema; shown as not extracted, never inferred from strength.",
                    "verification": verification,
                    "accuracy_tested": False,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                })
                return

            if path == "/api/compare":
                day_data, day_mime = decode_upload(payload.get("daylight", {}))
                indoor_data, indoor_mime = decode_upload(payload.get("indoor", {}))
                day = extract_photo_fields(day_data, day_mime, gemini_client())
                indoor = extract_photo_fields(indoor_data, indoor_mime, gemini_client())
                if day.status != "ok" or indoor.status != "ok":
                    self._send({
                        "error": "Gemini extraction did not succeed for both images; no reconciliation was invented.",
                        "daylight_status": day.status,
                        "indoor_status": indoor.status,
                        "daylight_message": day.message,
                        "indoor_message": indoor.message,
                        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
                    }, 502)
                    return
                view = compare_fields_view(day.fields.model_dump(), indoor.fields.model_dump(), "UI-PAIR")
                view["daylight_fields"] = day.fields.model_dump()
                view["indoor_fields"] = indoor.fields.model_dump()
                view["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
                self._send(view)
                return

            if path == "/api/compare_dataset":
                medicine_id = str(payload.get("medicine_id", ""))
                rows = read_csv_rows(DEFAULT_PACKAGE_RESULTS)
                pairs = {row["medicine_id"]: row for row in rows}
                if medicine_id not in pairs:
                    self._send({"error": "Unknown medicine id"}, 404)
                    return
                # Rebuild image-level field maps from the preserved reconciled row.
                row = pairs[medicine_id]
                fields = {
                    "brand_name": row["brand_name"],
                    "registration_number": row["nafdac_registration_number"],
                    "manufacturer": row["manufacturer"],
                    "strength": row["strength"],
                    "package_volume": row["package_volume"],
                }
                view = compare_fields_view(fields, fields, medicine_id)
                view["source"] = "data/packaging/ocr_results.csv (preserved image-level records)"
                self._send(view)
                return

            if path == "/api/decisions":
                cases = build_sms_cases(ENGINE)
                output = []
                for case in cases:
                    view = verification_view(case.result)
                    view.update({
                        "number": case.number,
                        "title": case.title,
                        "original": case.original_input,
                        "observed": observation_view(case.observation),
                    })
                    output.append(view)
                self._send({"cases": output, "expected_statuses": [
                    "MATCH", "PARTIAL_MATCH", "MISMATCH", "NO_MATCH",
                    "INSUFFICIENT_INFORMATION", "MANUAL_REVIEW_REQUIRED"
                ]})
                return

            if path == "/api/packages":
                rows = read_csv_rows(DEFAULT_PACKAGE_RESULTS)
                observations = [MedicineObservation.from_package_result(row) for row in rows]
                results = ENGINE.verify_package_results()
                output = []
                for observation, result in zip(observations, results):
                    view = verification_view(result)
                    view["observed"] = observation_view(observation)
                    output.append(view)
                self._send({
                    "records": output,
                    "total": len(output),
                    "any_forced_match": any(item["status"] == "MATCH" for item in output),
                    "pack_10_manual_review": next(
                        (item["manual_review"] for item in output if item["observation_id"] == "PACK-pack_10"),
                        None,
                    ),
                    "accuracy_tested": False,
                })
                return

            self._send({"error": "Not found"}, 404)
        except (ValueError, binascii.Error, KeyError) as exc:
            self._send({"error": f"{type(exc).__name__}: visible input error"}, 400)
        except Exception as exc:
            self._send({"error": type(exc).__name__}, 500)


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Drug SMS Checker local tester: http://{HOST}:{PORT}")
    print("Gemini availability is shown in the page header; no API key is displayed.")
    print("Offline sections remain usable when Gemini is unavailable. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local tester...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
