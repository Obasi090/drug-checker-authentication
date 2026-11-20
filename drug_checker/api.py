"""The web address (API) the website calls.

Install Flask once, inside your .venv:
    pip install flask

Run it from the PROJECT ROOT:
    python -m your_package_name.api
It listens on http://127.0.0.1:5000 (only this computer).

To let a phone on the same Wi-Fi reach it (for a demo on a network you trust):
    python -m your_package_name.api --host 0.0.0.0

Endpoints
    GET  /api/health         is it running, how many drugs, how fresh
    POST /api/check          {"message": "ventolin"}
                             -> {"findings": {...}, "sms_reply": "..."}
    POST /api/check-packet   {"brand_name": "...", "reg_number": "...",
                              "manufacturer": "...", "strength": "..."}
                             -> {"findings": {...}}   (with "mismatches")

Photos never come here. The photo is read first, the user confirms what was
read, and only that TEXT is sent to /api/check-packet.
"""
import argparse
import logging
import os
import sys

from flask import Flask, g, jsonify, request

from .ai_integration import (
    PHOTO_MAX_BYTES,
    PHOTO_TYPES,
    ai_capabilities,
    check_message_with_ai,
    explain_findings,
    extract_visible_fields,
)
from .config import DB_PATH, LOG_PATH
from .database import create_connection
from .db_ops import (
    count_drugs,
    get_alert_data_status,
    get_data_as_of,
    get_registry_data_status,
)
from .engine import MAX_MESSAGE_LENGTH, check_packet
from .logging_config import setup_logging
from .sms_replies import build_sms

logger = logging.getLogger(__name__)

DEFAULT_ORIGINS = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"


def _allowed_origins() -> set:
    raw = os.environ.get("ALLOWED_ORIGINS", DEFAULT_ORIGINS)
    return {origin.strip() for origin in raw.split(",") if origin.strip()}


def _error(message: str, status: int):
    return jsonify({"error": message}), status


def _json_body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else None


def create_app() -> Flask:
    app = Flask(__name__)
    # JSON checks are small; photo uploads are capped at 5 MB plus multipart overhead.
    app.config["MAX_CONTENT_LENGTH"] = 6 * 1024 * 1024
    try:
        app.json.sort_keys = False
    except AttributeError:
        pass

    allowed = _allowed_origins()

    def registry_scope(status):
        source = str((status or {}).get("source_name") or "").casefold()
        return "sample_demo" if "sample/demo" in source or "demo dataset" in source else "unknown"

    # One database connection per request, always closed afterwards
    def get_db():
        if "db" not in g:
            g.db = create_connection(DB_PATH)
        return g.db

    @app.teardown_appcontext
    def close_db(_error_unused):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.after_request
    def add_cors_headers(response):
        origin = request.headers.get("Origin")
        if origin in allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    @app.get("/api/health")
    def health():
        db = get_db()
        if db is None:
            return _error("Database unavailable", 503)
        return jsonify({
            "status": "ok",
            "drugs": count_drugs(db),
            "data_as_of": get_data_as_of(db),
            "registry_data_status": get_registry_data_status(db),
            "registry_scope": registry_scope(get_registry_data_status(db)),
            "alert_data_status": get_alert_data_status(db),
            "ai_capabilities": ai_capabilities(),
        })

    @app.post("/api/check")
    def check():
        body = _json_body()
        if body is None or not isinstance(body.get("message"), str):
            return _error('Send JSON like {"message": "ventolin"}', 400)

        if len(body["message"]) > MAX_MESSAGE_LENGTH * 4:
            return _error("Message too long", 400)

        db = get_db()
        if db is None:
            return _error("Database unavailable", 503)

        findings = check_message_with_ai(db, body["message"])
        return jsonify({
            "findings": findings,
            "sms_reply": build_sms(findings),
            "explanation": explain_findings(body["message"], findings),
        })

    @app.post("/api/check-packet")
    def check_packet_route():
        body = _json_body()
        if body is None:
            return _error("Send a JSON object with the details read from the box", 400)

        db = get_db()
        if db is None:
            return _error("Database unavailable", 503)

        try:
            findings = check_packet(db, body)
        except TypeError as error:
            return _error(str(error), 400)

        return jsonify({"findings": findings})

    @app.post("/api/photo/extract")
    def extract_photo_route():
        upload = request.files.get("image")
        if upload is None:
            return _error('Send a multipart image in the "image" field', 400)
        mime_type = (upload.mimetype or "").lower()
        if mime_type not in PHOTO_TYPES:
            return _error("Unsupported image type. Use JPEG, PNG or WebP.", 415)
        image_bytes = upload.stream.read(PHOTO_MAX_BYTES + 1)
        if not image_bytes:
            return _error("The image is empty", 400)
        if len(image_bytes) > PHOTO_MAX_BYTES:
            return _error("The image is larger than 5 MB", 413)
        signatures = {
            "image/jpeg": image_bytes.startswith(b"\xff\xd8\xff"),
            "image/png": image_bytes.startswith(b"\x89PNG\r\n\x1a\n"),
            "image/webp": (
                len(image_bytes) >= 12
                and image_bytes[:4] == b"RIFF"
                and image_bytes[8:12] == b"WEBP"
            ),
        }
        if not signatures.get(mime_type, False):
            return _error("Image content does not match its declared type", 415)
        result = extract_visible_fields(image_bytes, mime_type)
        del image_bytes
        # OCR output is always unconfirmed and cannot trigger a backend lookup.
        result["confirmed"] = False
        result["physical_authentication"] = False
        return jsonify(result)

    @app.post("/api/photo/compare")
    def compare_confirmed_photo_route():
        body = _json_body()
        if body is None:
            return _error("Send a JSON object with confirmed photo fields", 400)
        if body.get("confirmed") is not True:
            return _error("Confirm or correct the extracted fields before lookup", 400)
        fields = body.get("fields")
        if not isinstance(fields, dict):
            return _error('"fields" must be a JSON object', 400)
        allowed_fields = {
            "brand_name", "registration_number", "reg_number", "manufacturer", "strength"
        }
        if set(fields) - allowed_fields:
            return _error("Unsupported confirmed field", 400)
        if "registration_number" in fields and "reg_number" in fields:
            if fields["registration_number"] != fields["reg_number"]:
                return _error("Conflicting registration-number fields", 400)
        details = {
            "brand_name": fields.get("brand_name"),
            "reg_number": fields.get("registration_number", fields.get("reg_number")),
            "manufacturer": fields.get("manufacturer"),
            "strength": fields.get("strength"),
        }
        db = get_db()
        if db is None:
            return _error("Database unavailable", 503)
        try:
            findings = check_packet(db, details)
        except TypeError as error:
            return _error(str(error), 400)
        return jsonify({
            "confirmed": True,
            "findings": findings,
            "sms_reply": build_sms(findings),
            "explanation": explain_findings("confirmed package fields", findings),
        })

    @app.errorhandler(404)
    def not_found(_e):
        return _error("Not found", 404)

    @app.errorhandler(405)
    def method_not_allowed(_e):
        return _error("Method not allowed", 405)

    @app.errorhandler(413)
    def too_large(_e):
        return _error("Request too large", 413)

    @app.errorhandler(Exception)
    def unexpected(error):
        # Do not leak internal details to the browser
        logger.exception("Unhandled error: %s", error)
        return _error("Something went wrong. Please try again.", 500)

    return app


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run the drug checker API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args(argv)

    setup_logging(LOG_PATH)
    logger.info("Starting the API on %s:%s", args.host, args.port)

    create_app().run(host=args.host, port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())