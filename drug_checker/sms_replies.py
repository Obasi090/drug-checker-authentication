"""Turn FINDINGS (from engine.py) into a short SMS reply.

Rules:
  * Aim for 160 characters, so the reply is one SMS.
  * Plain ASCII only. One accented or fancy character would switch the
    whole message to a format that fits only 70 characters.
  * Square brackets and a few other symbols cost 2 characters each in SMS,
    so reg numbers go in round brackets.
  * Never say "safe", "genuine" or "fake". Never give medical advice.
  * Always say how recent the data is, when we know.
"""
import re
import unicodedata
from datetime import datetime
from urllib.parse import urlparse

SMS_LIMIT = 160

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_REPLACEMENTS = {
    "[": "(", "]": ")", "{": "(", "}": ")",
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u00a0": " ",
}
_DROP = "|^~\\`\u20ac"

HELP_TEXT = (
    "Send a drug name (e.g. Panadol) or the reg no on the box "
    "(e.g. A4-1234)."
)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

def _gsm_safe(text: str) -> str:
    for old, new in _REPLACEMENTS.items():
        text = text.replace(old, new)

    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = "".join(ch for ch in text if ch not in _DROP)

    return " ".join(text.split())


def _clip(text, limit: int) -> str:
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 1)].rstrip() + "..."


def _fit(options) -> str:
    """Return the first option that fits in one SMS."""
    for option in options:
        text = _gsm_safe(option)
        if len(text) <= SMS_LIMIT:
            return text

    return _clip(_gsm_safe(options[-1]), SMS_LIMIT)


def _short_date(iso):
    try:
        parsed = datetime.strptime(iso, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None
    return f"{parsed.day} {_MONTHS[parsed.month - 1]} {parsed.year}"


def _as_of(findings) -> str:
    date = _short_date(findings.get("data_as_of"))
    return f" as of {date}" if date else ""


def _source_name(link) -> str:
    host = urlparse(link or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _registry_coverage_note(findings) -> str:
    status = findings.get("registry_data_status") or {}
    source = str(status.get("source_name") or "").casefold()
    if "sample/demo" in source or "demo dataset" in source:
        return "Demo sample only; coverage is limited."
    return ""


def _alert_availability(findings) -> str:
    """Describe an empty alert result without overstating source coverage."""
    status = (findings.get("alert_data_status") or {}).get("status", "unknown")
    if status == "loaded":
        return "No alert matched in checked data."
    if status == "stale":
        return "Alert data is stale."
    if status == "error":
        return "Alert data check failed."
    return "Alert data status unknown."


# ----------------------------------------------------------------------
# One builder per kind of answer
# ----------------------------------------------------------------------

def _invalid(findings) -> str:
    reason = findings.get("reason")

    if reason == "scratch_code":
        return _fit([
            "That looks like a scratch code. We cannot check those. Text it "
            "to the MAS short code printed on your pack.",
            "That looks like a scratch code. Text it to the MAS short code "
            "on your pack.",
        ])

    if reason == "too_long":
        return _fit(["Message too long. " + HELP_TEXT])

    return _fit([HELP_TEXT])


def _alert_text(findings, name, reg) -> str:
    alerts = findings["alerts"]
    first = alerts[0]
    extra = len(alerts) - 1

    kind = first["alert_type"].upper()
    date = _short_date(first["alert_date"]) or first["alert_date"]
    source = _source_name(first["source_link"])
    reason = first["reason"]
    label = f"{name} ({reg})" if reg else name
    more = f" (+{extra} more alert{'s' if extra > 1 else ''})" if extra > 0 else ""

    if first.get("source_kind") == "synthetic":
        return _fit([
            f"SYNTHETIC DEMO ONLY: {label} {kind} ({date}). Not a real NAFDAC notice. {more}",
            f"DEMO ONLY, not a real NAFDAC notice: {kind} for {label}.",
        ])

    if first["matched_by"] != "reg_number":
        return _fit([
            f"An alert may apply to {label}: {kind} on {date}, matched by "
            f"name only. Compare the reg no. Ask NAFDAC.{more}",
            f"An alert may apply to {_clip(name, 35)}: {kind} on {date} "
            f"(name match only). Ask NAFDAC.",
            f"Possible alert: {kind} on {date}. Ask NAFDAC.",
        ])

    if not first["active"]:
        cleared = _short_date(first["resolved_date"]) or first["resolved_date"]
        return _fit([
            f"{label}: earlier alert {kind} on {date}, cleared {cleared}. "
            f"Ask NAFDAC if unsure.{more}",
            f"{_clip(name, 40)}: earlier alert {kind} on {date}, cleared "
            f"{cleared}.",
        ])

    base = f"ALERT: {label} - {kind} on {date}."
    options = []
    if reason and source:
        options.append(f"{base} Reason: {_clip(reason, 50)}. Source: {source}. Ask NAFDAC before use.{more}")
    if reason:
        options.append(f"{base} Reason: {_clip(reason, 40)}. Ask NAFDAC before use.{more}")
    if source:
        options.append(f"{base} Source: {source}. Ask NAFDAC before use.")
    options += [
        f"{base} Ask NAFDAC before use.",
        f"ALERT: {_clip(name, 40)} - {kind} on {date}. Ask NAFDAC.",
    ]
    return _fit(options)


def _found(findings) -> str:
    match = findings["matches"][0]
    name, reg = match["brand_name"], match["reg_number"]
    status = match["registry_status"] or "unknown"
    as_of = _as_of(findings)
    coverage_note = _registry_coverage_note(findings)

    if findings["alerts"]:
        return _alert_text(findings, name, reg)

    if status.lower() != "active":
        return _fit([
            f"{name} ({reg}): registry status {status.upper()}. Ask NAFDAC or "
            f"a pharmacist. {_alert_availability(findings)} {coverage_note}{as_of}",
            f"{_clip(name, 45)} ({reg}): registry status {status.upper()}. "
            f"Ask NAFDAC or a pharmacist.",
        ])

    alert_note = _alert_availability(findings)
    options = []
    if match["manufacturer"]:
        options.append(
            f"{name} ({reg}) is in the loaded registry data (status: {status}). "
            f"Maker: {match['manufacturer']}. {alert_note} {coverage_note}{as_of}"
        )
    options += [
        f"{name} ({reg}) matches loaded registry data (status: {status}). "
        f"{alert_note} {coverage_note}{as_of}",
        f"{_clip(name, 45)} ({reg}): registry {status}. {alert_note} {coverage_note}{as_of}",
        f"{_clip(name, 30)} ({reg}): {status}. {alert_note} {coverage_note}{as_of}",
    ]
    return _fit(options)


def _multiple(findings) -> str:
    matches = findings["matches"]
    query = _clip(findings["query"], 20)
    total = len(matches)
    count = f"{total}+" if findings.get("more_results") else str(total)

    # Preserve a notice when present; otherwise disclose whether alert data
    # was checked, stale, unavailable, or unknown.
    alert_note = (
        " Alerts exist on some."
        if findings["alerts"]
        else " " + _alert_availability(findings)
    )
    coverage_note = _registry_coverage_note(findings)

    if findings["query_type"] == "reg_number":
        options = []
        for shown in (3, 2, 1):
            names = "; ".join(_clip(m["brand_name"], 28) for m in matches[:shown])
            left = total - shown
            tail = f" (+{left} more)" if left > 0 else ""
            options.append(
                f"{total} products share reg no {query}: {names}{tail}. "
                f"Text the full product name.{alert_note} {coverage_note}"
            )
        options.append(f"{total} products share reg no {query}. Text the full product name.{alert_note} {coverage_note}")
        return _fit(options)

    options = []
    for shown in (3, 2, 1):
        items = "; ".join(
            f"{_clip(m['brand_name'], 24)} ({m['reg_number']})" for m in matches[:shown]
        )
        left = total - shown
        tail = f" (+{left} more)" if left > 0 else ""
        options.append(
            f"{count} products match '{query}'. Text the reg no of yours: {items}{tail}.{alert_note} {coverage_note}"
        )
    options.append(
        f"Several products match '{query}'. Text the reg no from the box, e.g. A4-1234.{alert_note} {coverage_note}"
    )
    return _fit(options)


def _not_found(findings) -> str:
    alerts = findings["alerts"]
    query = _clip(findings["query"], 25)
    coverage_note = _registry_coverage_note(findings)

    if alerts:
        first = alerts[0]
        kind = first["alert_type"].upper()
        date = _short_date(first["alert_date"]) or first["alert_date"]
        if first.get("source_kind") == "synthetic":
            return _fit([
                f"No registry match in available data. SYNTHETIC DEMO ONLY: {kind} "
                f"on {date}. Not a real NAFDAC notice. {coverage_note}",
                f"DEMO ONLY, not a real NAFDAC notice: synthetic {kind} on {date}.",
            ])
        return _fit([
            f"Not in our registry, but an alert exists: {kind} on {date} "
            f"({_clip(first['product_name'], 30)}). {coverage_note} Ask NAFDAC.",
            f"No record in the available registry data; alert {kind} on {date}. {coverage_note} Ask NAFDAC.",
        ])

    subject = f"reg no {query}" if findings["query_type"] == "reg_number" else f"'{query}'"
    as_of = _as_of(findings)
    alert_status = (findings.get("alert_data_status") or {}).get("status", "unknown")
    alert_note = _alert_availability(findings)
    return _fit([
        f"We have no record of {subject}{as_of}. This does not mean it is "
        f"unsafe or fake. {alert_note} {coverage_note} Ask NAFDAC or a pharmacist.",
        f"No record of {subject}{as_of}. Not found does not mean unsafe. "
        f"{alert_note} {coverage_note} Ask NAFDAC or a pharmacist.",
        f"No record of {subject}. {alert_note} {coverage_note} Ask NAFDAC.",
        # Preserve compact legacy wording only when checked data is known.
        f"No record of {subject}. Ask NAFDAC or a pharmacist."
        if alert_status != "unknown" else f"No record of {subject}. Alert data unknown."
    ])


# ----------------------------------------------------------------------
# The one function other code calls
# ----------------------------------------------------------------------

def build_sms(findings: dict) -> str:
    """Return the SMS reply for a findings dictionary."""
    status = findings.get("status")

    if status == "invalid":
        return _invalid(findings)
    if status == "found":
        return _found(findings)
    if status == "multiple":
        return _multiple(findings)
    if status == "not_found":
        return _not_found(findings)

    return _fit(["Sorry, we could not check that right now. Please try again."])
