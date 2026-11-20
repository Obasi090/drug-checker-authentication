"""Lazy adapter from optional AI/ML helpers to the authoritative backend.

The AI/ML package never opens a registry, decides a match, or creates alerts.
Every extracted query is handed to the deterministic drug_checker engine.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from .db_ops import get_searchable_names
from .engine import check_message
from .sms_replies import build_sms

logger = logging.getLogger(__name__)
AI_PACKAGE = "drug_sms_checker_AI_ML.src"
PHOTO_MAX_BYTES = 5 * 1024 * 1024
PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _load_message_parser():
    try:
        module = importlib.import_module(f"{AI_PACKAGE}.message")
        return module.parse_message
    except (ImportError, ModuleNotFoundError):
        return None


def _load_gemini_client():
    try:
        module = importlib.import_module(f"{AI_PACKAGE}.gemini")
        return module.GeminiClient()
    except (ImportError, ModuleNotFoundError):
        return None


def message_extractor(conn):
    """Build an optional structured extractor using names from this registry."""
    parser = _load_message_parser()
    if parser is None:
        return None
    known_names = get_searchable_names(conn)

    def extract(text: str):
        intent = parser(text, known_names)
        if getattr(intent, "medical_question", False):
            return intent
        if not getattr(intent, "needs_clarification", True):
            return intent

        client = _load_gemini_client()
        if client is None or not client.available:
            return intent
        exact = client.extract_intent(text)
        reg = getattr(exact, "registration_number", None)
        name = getattr(exact, "name", None)
        if reg:
            # A model may only nominate a span. The backend's own format
            # classifier must also accept it before registration lookup.
            from .engine import classify_message
            query_type, _, reason = classify_message(reg)
            if query_type == "reg_number" and reason is None and reg in text:
                return {
                    "intent": "lookup",
                    "registration_number": reg,
                    "needs_clarification": False,
                    "medical_question": False,
                }
        if name and name in text:
            return {
                "intent": "lookup",
                "name": name,
                "needs_clarification": False,
                "medical_question": False,
            }
        return intent

    return extract


def check_message_with_ai(conn, text: Any) -> dict:
    """Parse conservatively, then let only the backend produce findings."""
    try:
        extractor = message_extractor(conn)
    except Exception:
        logger.warning("Optional message extraction unavailable; using backend parser")
        extractor = None
    return check_message(conn, text, extractor=extractor)


def explain_findings(question: str, findings: dict) -> dict[str, Any]:
    """Explain a copy of backend findings; never mutate or replace the result."""
    try:
        contracts = importlib.import_module(f"{AI_PACKAGE}.contracts")
        adapted = contracts.adapt_findings(findings)
        client = _load_gemini_client()
        if client is None:
            raise ImportError("Gemini dependencies are unavailable")
        result = client.explain(question, adapted)
        if client.available and not result.used_fallback and not result.used_mock:
            mode = "gemini"
        elif result.used_fallback:
            mode = "fallback"
        else:
            mode = "deterministic"
        return {
            "text": result.reply,
            "mode": mode,
            "safety_action": result.safety_action or None,
        }
    except Exception:
        # Includes missing optional packages, invalid model output, and wrapper
        # failures. Do not log exception text because upstream details may leak.
        logger.warning("Optional explanation unavailable; deterministic fallback used")
        return {"text": build_sms(findings), "mode": "deterministic", "safety_action": None}


def extract_visible_fields(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    """Read visible text only; return unconfirmed fields and never retain bytes."""
    try:
        photo = importlib.import_module(f"{AI_PACKAGE}.photo")
        client = _load_gemini_client()
        result = photo.extract_photo_fields(image_bytes, mime_type, client=client)
        fields = result.fields.model_dump()
        return {
            "fields": fields,
            "status": result.status,
            "accuracy_tested": result.accuracy_tested,
            "message": result.message,
            "confirmed": False,
        }
    except Exception:
        logger.warning("Optional photo reader unavailable")
        return {
            "fields": {
                "brand_name": "not visible",
                "registration_number": "not visible",
                "manufacturer": "not visible",
                "strength": "not visible",
            },
            "status": "unavailable",
            "accuracy_tested": False,
            "message": "Photo reading is unavailable; no fields were extracted.",
            "confirmed": False,
        }
    finally:
        del image_bytes


def ai_capabilities() -> dict[str, str]:
    """Describe capability availability without exposing any credential value."""
    parser = _load_message_parser()
    if parser is None:
        return {"message_parser": "unavailable", "gemini": "optional dependencies missing"}
    client = _load_gemini_client()
    if client is None:
        return {"message_parser": "available", "gemini": "optional dependencies missing"}
    return {
        "message_parser": "available",
        "gemini": "configured" if client.available else "not configured",
    }
