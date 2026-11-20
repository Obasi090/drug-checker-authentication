"""The checking engine.

This module accepts a user message or user-confirmed packaging details,
checks the registry and regulatory alerts, and returns structured findings.

It does not write SMS replies and never decides that a medicine or pack is
safe, genuine, or fake.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

from .db_ops import (
    find_alerts,
    find_by_name,
    find_by_reg_number,
    get_alert_data_status,
    get_data_as_of,
    get_registry_data_status,
    normalize_name,
    normalize_reg_number,
)

logger = logging.getLogger(__name__)

MAX_MESSAGE_LENGTH = 200
MAX_MATCHES = 10
MIN_NAME_LENGTH = 2

# Greenbook examples include A4-102585, C4-1652, 04-0519 and A11-101414.
_REG_WITH_HYPHEN = re.compile(r"^[A-Za-z0-9]{1,4}-\d{3,7}$")
_REG_COMPACT = re.compile(r"^[A-Za-z]?\d{5,9}$")
_STRIP_CHARS = " .,;:!?\"'()[]{}"

_NOT_VISIBLE = {
    "", "not visible", "not visible.", "n/a", "na", "none", "unknown", "null"
}

_COMPANY_NOISE = {
    "ltd", "limited", "pvt", "plc", "inc", "co", "company", "nigeria",
    "nig", "llc", "private", "pharmaceuticals", "pharmaceutical",
    "pharma", "pharmacy", "laboratories", "laboratory", "labs",
    "healthcare", "health", "care", "industries", "international",
    "india", "formulations",
}

_MATCH_FIELDS = (
    "product_id",
    "reg_number",
    "brand_name",
    "generic_name",
    "manufacturer",
    "applicant",
    "strength",
    "dosage_form",
    "pack_size",
    "category",
    "marketing_category",
    "registry_status",
    "approved_at",
    "expires_at",
    "detail_url",
    "data_quality_note",
    "source",
)


# ---------------------------------------------------------------------------
# Message cleaning and basic classification
# ---------------------------------------------------------------------------

def clean_message(text: Any) -> str:
    """Normalize Unicode, dash characters, whitespace and outer punctuation."""
    if not isinstance(text, str):
        return ""

    value = unicodedata.normalize("NFKC", text)
    value = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015]", "-", value)
    value = "".join(
        char if (char.isprintable() or char.isspace()) else " "
        for char in value
    )
    value = " ".join(value.split())
    return value.strip(_STRIP_CHARS)


def classify_message(text: Any) -> tuple[str | None, str, str | None]:
    """Return (query_type, value, reason).

    query_type is "name" or "reg_number". A reason means no lookup should run.
    """
    cleaned = clean_message(text)

    if not cleaned:
        return None, "", "empty"

    if len(cleaned) > MAX_MESSAGE_LENGTH:
        return None, "", "too_long"

    # Long digit-only values may be one-time scratch codes. Never look them up.
    compact = cleaned.replace(" ", "").replace("-", "")
    if compact.isdigit() and 10 <= len(compact) <= 16:
        return None, "", "scratch_code"

    for token in cleaned.split():
        token = token.strip(_STRIP_CHARS)
        if _REG_WITH_HYPHEN.fullmatch(token) or _REG_COMPACT.fullmatch(token):
            return "reg_number", token, None

    return "name", cleaned, None


# ---------------------------------------------------------------------------
# Findings construction
# ---------------------------------------------------------------------------

def _invalid_findings(query: str, reason: str) -> dict:
    return {
        "query": query,
        "query_type": None,
        "status": "invalid",
        "reason": reason,
        "matches": [],
        "more_results": False,
        "alerts": [],
        "has_active_alert": False,
        "mismatches": [],
        "data_as_of": None,
        "registry_data_status": {"status": "unknown", "timestamp_trustworthy": False},
        "alert_data_status": {"status": "unknown", "timestamp_trustworthy": False},
    }


def _match_dict(row) -> dict:
    """Copy the registry fields expected by the shared findings contract."""
    result = {field: row[field] for field in _MATCH_FIELDS}
    if "match_rank" in row.keys():
        result["match_rank"] = row["match_rank"]
    return result


def _alert_dict(row, matched_by: str, product_id: int | None) -> dict:
    return {
        "id": row["id"],
        "reg_number": row["reg_number"],
        "product_name": row["product_name"],
        "alert_type": row["alert_type"],
        "alert_date": row["alert_date"],
        "reason": row["reason"],
        "source_link": row["source_link"],
        "source_kind": row["source_kind"] if "source_kind" in row.keys() else "unknown",
        "demo_label": (
            "SYNTHETIC — DEMONSTRATION ONLY"
            if "source_kind" in row.keys() and row["source_kind"] == "synthetic"
            else None
        ),
        "resolved_date": row["resolved_date"],
        "active": row["resolved_date"] is None,
        "matched_by": matched_by,
        "product_id": product_id,
    }


def _alerts_for_drug(conn, drug_row) -> list[dict]:
    """Return alerts that can reasonably be associated with one registry row."""
    applicable = []

    for alert in find_alerts(
        conn,
        reg_number=drug_row["reg_number"],
        name=drug_row["brand_name"],
    ):
        if alert["reg_number_normalized"] == drug_row["reg_number_normalized"]:
            matched_by = "reg_number"
        elif (
            alert["reg_number_normalized"] is None
            and alert["product_name_normalized"] == drug_row["name_normalized"]
        ):
            matched_by = "name"
        else:
            # A notice explicitly carrying another registration number must
            # not be attached merely because its product name is similar.
            continue

        applicable.append(
            _alert_dict(alert, matched_by, drug_row["product_id"])
        )

    return applicable


def _dedupe_alerts(alerts: list[dict]) -> list[dict]:
    """Remove duplicate copies of the same notice."""
    seen = set()
    unique = []

    for alert in alerts:
        key = (
            alert["id"],
            alert["alert_type"],
            alert["alert_date"],
            alert["source_link"],
            alert["product_id"],
        )
        if key not in seen:
            seen.add(key)
            unique.append(alert)

    return unique


def _sort_alerts(alerts: list[dict]) -> list[dict]:
    """Order active alerts first, then registration matches, then newest."""
    alerts.sort(key=lambda item: item["alert_date"], reverse=True)
    alerts.sort(
        key=lambda item: (
            not item["active"],
            item["matched_by"] != "reg_number",
        )
    )
    return alerts


def _build_findings(
    conn,
    query: str,
    query_type: str,
    rows: list,
    more_results: bool,
) -> dict:
    if rows:
        alerts = []
        for row in rows:
            alerts.extend(_alerts_for_drug(conn, row))
    elif query_type == "reg_number":
        # A notice can exist even when its product is absent from Greenbook.
        alerts = [
            _alert_dict(alert, "reg_number", None)
            for alert in find_alerts(conn, reg_number=query)
        ]
    else:
        # With no registry row, name-only discovery is weaker evidence.
        alerts = [
            _alert_dict(alert, "name", None)
            for alert in find_alerts(conn, name=query)
        ]

    alerts = _sort_alerts(_dedupe_alerts(alerts))

    if not rows:
        status = "not_found"
    elif len(rows) == 1 and not more_results:
        status = "found"
    else:
        status = "multiple"

    registry_status = get_registry_data_status(conn)
    registry_source = str(registry_status.get("source_name") or "").casefold()
    registry_scope = "sample_demo" if "sample/demo" in registry_source else "unknown"

    return {
        "query": query,
        "query_type": query_type,
        "status": status,
        "reason": None,
        "matches": [_match_dict(row) for row in rows],
        "more_results": more_results,
        "alerts": alerts,
        "has_active_alert": any(alert["active"] for alert in alerts),
        "mismatches": [],
        "data_as_of": get_data_as_of(conn),
        "registry_data_status": registry_status,
        "registry_scope": registry_scope,
        "alert_data_status": get_alert_data_status(conn),
    }


# ---------------------------------------------------------------------------
# Registry lookups
# ---------------------------------------------------------------------------

def check_name(conn, name: str, limit: int = MAX_MATCHES) -> dict:
    """Search by exact brand name, prefix, internal word, or ingredient."""
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit < 1
    ):
        raise ValueError("limit must be a positive integer")

    query = clean_message(name)

    try:
        normalized = normalize_name(query)
    except (TypeError, ValueError):
        return _invalid_findings("", "empty")

    if len(normalized) < MIN_NAME_LENGTH:
        return _invalid_findings(query, "too_short")

    # One extra row tells us whether the search has more results than shown.
    rows = list(find_by_name(conn, query, limit=limit + 1))

    exact = [row for row in rows if row["match_rank"] == 0]
    if exact:
        # Exact results take precedence over looser suggestions. Still report
        # additional exact results if they exceed the requested display limit.
        more_results = len(exact) > limit
        rows = exact[:limit]
    else:
        more_results = len(rows) > limit
        rows = rows[:limit]

    return _build_findings(conn, query, "name", rows, more_results)


def check_reg_number(conn, reg_number: str) -> dict:
    """Find all registry products carrying the supplied registration number."""
    query = clean_message(reg_number)

    try:
        normalize_reg_number(query)
    except (TypeError, ValueError):
        return _invalid_findings("", "empty")

    rows = list(find_by_reg_number(conn, query))
    return _build_findings(conn, query, "reg_number", rows, False)


# ---------------------------------------------------------------------------
# Message parser integration
# ---------------------------------------------------------------------------

def _intent_values(extracted: Any) -> dict | None:
    """Adapt either MessageIntent/Pydantic output or a plain dictionary."""
    if extracted is None:
        return None

    if isinstance(extracted, dict):
        return extracted

    # Pydantic v2 model, including the MessageIntent model.
    model_dump = getattr(extracted, "model_dump", None)
    if callable(model_dump):
        result = model_dump()
        return result if isinstance(result, dict) else None

    # A small accommodation for simple objects exposing the same attributes.
    attributes = (
        "intent",
        "medical_question",
        "needs_clarification",
        "registration_number",
        "name",
    )
    if any(hasattr(extracted, field) for field in attributes):
        return {
            field: getattr(extracted, field, None)
            for field in attributes
        }

    return None


def check_message(conn, text: Any, extractor=None) -> dict:
    """Parse a raw message and perform a registry lookup when appropriate.

    `extractor`, when supplied, should return a MessageIntent-like object or
    a dictionary. If omitted, the project's deterministic parse_message()
    function is used. The built-in classifier is the final fallback.
    """
    cleaned = clean_message(text)

    if not cleaned:
        return _invalid_findings("", "empty")

    if len(cleaned) > MAX_MESSAGE_LENGTH:
        return _invalid_findings(cleaned, "too_long")

    # The production package has no optional NLP parser module. Keep message
    # extraction deterministic unless a caller explicitly injects an extractor.
    parser = extractor

    extracted = None
    if parser is not None:
        try:
            extracted = _intent_values(parser(cleaned))
        except Exception:
            logger.exception("Message parser failed; using built-in rules")

    if extracted:
        if extracted.get("medical_question"):
            return _invalid_findings(cleaned, "medical_question")

        intent = extracted.get("intent")
        if intent == "medical_question":
            return _invalid_findings(cleaned, "medical_question")

        if extracted.get("needs_clarification") is True:
            return _invalid_findings(cleaned, "clarification_required")

        registration_number = (
            extracted.get("registration_number")
            or extracted.get("reg_number")
        )
        name = extracted.get("name")

        if registration_number:
            return check_reg_number(conn, registration_number)

        if name:
            return check_name(conn, name)

        if intent == "lookup":
            # The parser says this is a lookup but supplied no usable field.
            return _invalid_findings(cleaned, "clarification_required")

    # Basic rules remain available if the parser cannot extract a query.
    query_type, value, reason = classify_message(cleaned)

    if reason:
        return _invalid_findings(cleaned, reason)

    if query_type == "reg_number":
        return check_reg_number(conn, value)

    findings = check_name(conn, value)

    # A second chance for unfamiliar registration-number formats, but only
    # after an unsuccessful name lookup.
    if (
        findings["status"] == "not_found"
        and not findings["alerts"]
        and _REG_WITH_HYPHEN.fullmatch(value.strip(_STRIP_CHARS))
    ):
        return check_reg_number(conn, value.strip(_STRIP_CHARS))

    return findings


# ---------------------------------------------------------------------------
# Packaging comparison helpers
# ---------------------------------------------------------------------------

def _box_value(details: dict, field: str) -> str | None:
    value = details.get(field)

    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string or None")

    value = " ".join(value.split())
    return None if value.casefold() in _NOT_VISIBLE else value


def _name_tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", normalize_name(value)))


def _name_matches(box_name: str, record_name: str) -> bool:
    """Return True only for exact or strong containment-style name agreement."""
    try:
        box = normalize_name(box_name)
        record = normalize_name(record_name)
    except (TypeError, ValueError):
        return False

    return box == record or box in record or record in box


def _company_tokens(value: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9]+", value.casefold()))
    significant = words - _COMPANY_NOISE
    return significant or words


def _company_matches(box_company: str, record_company: str | None) -> bool:
    if not record_company:
        return False

    box = _company_tokens(box_company)
    record = _company_tokens(record_company)
    return bool(box and record and (box <= record or record <= box))


_STRENGTH_TOKEN = re.compile(
    r"\d+(?:\.\d+)?(?:mcg|µg|μg|mg|kg|g|ml|l|iu|%)",
    re.IGNORECASE,
)


def _strength_tokens(value: str) -> set[str]:
    squashed = re.sub(r"\s+", "", value.casefold())
    squashed = squashed.replace("i.u.", "iu")
    squashed = squashed.replace("μg", "µg")
    return set(_STRENGTH_TOKEN.findall(squashed))


def _strength_matches(box_strength: str, record_strength: str | None) -> bool:
    """Compare explicit amount/unit tokens without converting units."""
    if not record_strength:
        return False

    box = _strength_tokens(box_strength)
    record = _strength_tokens(record_strength)

    if box and record:
        # Subset comparison accommodates a box showing a full composition.
        return box <= record or record <= box

    def squash(value: str) -> str:
        return re.sub(r"\s+", "", value.casefold())

    record_segments = [
        squash(part) for part in re.split(r"[;,]", record_strength)
    ]
    return (
        squash(box_strength) == squash(record_strength)
        or squash(box_strength) in record_segments
    )


def _mismatch(
    field: str,
    expected: Any,
    observed: Any,
    note: str,
) -> dict:
    """Use the shared contract's field names.

    expected = value in the registry; observed = value read from the box.
    """
    return {
        "field": field,
        "expected": expected,
        "observed": observed,
        "note": note,
    }


def _find_mismatches(conn, box: dict, findings: dict) -> list[dict]:
    """Report clear discrepancies; do not infer authenticity."""
    mismatches = []
    rows = findings["matches"]

    # The registration number was not found, but the name may exist under
    # another registration number. This is a discrepancy, not proof of fraud.
    if box["reg_number"] and not rows and box["brand_name"]:
        try:
            same_name = [
                row
                for row in find_by_name(conn, box["brand_name"], limit=MAX_MATCHES)
                if row["match_rank"] <= 2
            ]
        except (TypeError, ValueError):
            same_name = []

        if same_name:
            mismatches.append(
                _mismatch(
                    "reg_number",
                    sorted({row["reg_number"] for row in same_name}),
                    box["reg_number"],
                    (
                        "This number was not found in the registry. "
                        "Products with this name appear under other numbers."
                    ),
                )
            )

    if not rows:
        return mismatches

    if box["brand_name"]:
        if not any(
            _name_matches(box["brand_name"], row["brand_name"])
            for row in rows
        ):
            mismatches.append(
                _mismatch(
                    "brand_name",
                    sorted({row["brand_name"] for row in rows}),
                    box["brand_name"],
                    "The name on the box differs from the registered name.",
                )
            )

    if box["manufacturer"]:
        known = [
            row for row in rows
            if row["manufacturer"] or row["applicant"]
        ]
        if known and not any(
            _company_matches(box["manufacturer"], row["manufacturer"])
            or _company_matches(box["manufacturer"], row["applicant"])
            for row in known
        ):
            mismatches.append(
                _mismatch(
                    "manufacturer",
                    sorted({
                        value
                        for row in known
                        for value in (row["manufacturer"], row["applicant"])
                        if value
                    }),
                    box["manufacturer"],
                    (
                        "The company name on the box differs from the "
                        "manufacturer/applicant recorded in the registry."
                    ),
                )
            )

    if box["strength"]:
        known = [row for row in rows if row["strength"]]
        if known and not any(
            _strength_matches(box["strength"], row["strength"])
            for row in known
        ):
            # Only report a mismatch when both sides contain explicit
            # amount/unit tokens. Text-only comparisons are too uncertain.
            box_tokens = _strength_tokens(box["strength"])
            record_tokens = set().union(
                *(_strength_tokens(row["strength"]) for row in known)
            )
            if box_tokens and record_tokens and box_tokens.isdisjoint(record_tokens):
                mismatches.append(
                    _mismatch(
                        "strength",
                        sorted({row["strength"] for row in known}),
                        box["strength"],
                        (
                            "The explicit strength amounts/units on the box "
                            "do not agree with the registry values."
                        ),
                    )
                )

    return mismatches


def check_packet(conn, details: dict) -> dict:
    """Check user-confirmed fields extracted from a medicine package photo.

    Accepted keys: brand_name, reg_number, manufacturer, strength.
    The photo reader's registration_number must be mapped to reg_number by
    the caller, and the user must confirm the extracted values first.
    """
    if not isinstance(details, dict):
        raise TypeError("details must be a dictionary")

    box = {
        field: _box_value(details, field)
        for field in ("brand_name", "reg_number", "manufacturer", "strength")
    }

    findings = None

    if box["reg_number"]:
        findings = check_reg_number(conn, box["reg_number"])
        if findings["status"] == "invalid":
            findings = None

    # Do not silently switch to a name lookup when a validly-shaped
    # registration number simply has no registry result. The mismatch
    # comparison below can still check whether the name exists under another
    # number.
    if findings is None and box["brand_name"]:
        findings = check_name(conn, box["brand_name"])

    if findings is None:
        return _invalid_findings("", "nothing_to_check")

    findings["mismatches"] = _find_mismatches(conn, box, findings)
    return findings
