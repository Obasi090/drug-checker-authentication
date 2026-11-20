"""Deterministic message understanding.

Rules are deliberately conservative: a registration number is extracted first,
using only formats actually observed in the NAFDAC Greenbook sample saved in
``data/test_drugs.csv`` (for example 04-0858, A4-101970, A11-0236). Names come
from the text itself or from an approved catalogue supplied by the caller;
symptoms and context are never converted into a medicine name.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from pydantic import BaseModel, ConfigDict

# Hyphen glyphs observed/typed by users. The hyphen is part of the real NRN.
_HYPHEN = r"[-‐‑‒–—―]"
_REG_RE = re.compile(rf"(?<![A-Za-z0-9])([A-Z0-9]{{2,3}}{_HYPHEN}\d{{4,6}})(?![A-Za-z0-9])", re.IGNORECASE)

_LEADING_FILLERS = re.compile(
    r"^(?:abeg|please|pls|plz|hello|hi|hey|good\s+(?:morning|afternoon|evening)|"
    r"wetin\s+be|wetindey\s+for|wetin\s+dey\s+for|how\s+far\s+with|i\s+dey\s+find|abeg\s+tell\s+me\s+about|"
    r"i\s+(?:want|need)\s+(?:to\s+)?(?:check|know|see)|can\s+you\s+(?:help|check|tell\s+me)|"
    r"check|verify|search\s+for|find|what(?:'s|\s+is)\s+the\s+(?:status|registration)\s+of)"
    r"(?=[\s,:;-]|$)[\s,:;-]*",
    re.IGNORECASE,
)
_TRAILING_FILLERS = re.compile(
    r"(?:^|[\s,:;-]+)(?:please|pls|plz|abeg|thanks|thank\s+you|for\s+me|na|now|sef|sha|oh)[\s?.!]*$",
    re.IGNORECASE,
)
_MEDICAL_WORDS = re.compile(
    r"\b(dose|dosage|how\s+much|how\s+many|side\s+effect|interaction|overdose|"
    r"can\s+i\s+take|should\s+i\s+take|start|stop|pregnan|breastfeed|diagnos|"
    r"treat|symptom|allerg|contraindicat)\w*\b",
    re.IGNORECASE,
)


class MessageIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    original: str
    normalized: str
    registration_number: str | None = None
    name: str | None = None
    intent: str = "clarify"  # lookup | medical_question | clarify
    medical_question: bool = False
    needs_clarification: bool = True
    extracted_by: str = "none"  # deterministic | gemini | none
    notes: list[str] = []


def normalize(text: str) -> str:
    """NFKC-normalise, unify hyphens, lower-case and collapse whitespace."""
    value = unicodedata.normalize("NFKC", text or "")
    value = re.sub(r"[-‐‑‒–—―]", "-", value)
    return re.sub(r"\s+", " ", value).strip().lower()


def find_registration_number(text: str) -> str | None:
    """Return the exact registration-number span present in the original text."""
    if not text:
        return None
    match = _REG_RE.search(text)
    return match.group(1) if match else None


def strip_filler(text: str) -> str:
    """Remove only clearly safe leading/trailing filler, never inner words."""
    value = (text or "").strip()
    changed = True
    while changed:
        changed = False
        new = _LEADING_FILLERS.sub("", value, count=1)
        if new != value:
            value, changed = new, True
        new = _TRAILING_FILLERS.sub("", value, count=1)
        if new != value:
            value, changed = new, True
    return value.strip(" \t\r\n,:;-?.!")


def is_medical_question(text: str) -> bool:
    value = text or ""
    if len(value.split()) <= 2 and "?" not in value:
        return False  # one or two words with no question: far more likely a product name
    return bool(_MEDICAL_WORDS.search(value))


def name_from_catalogue(normalized_text: str, known_names: Iterable[str]) -> str | None:
    """Return the longest known catalogue name that occurs in the text."""
    matches = [n for n in known_names if n and normalize(n) in normalized_text]
    if not matches:
        return None
    return max(matches, key=lambda n: len(normalize(n)))


_NON_NAME_TOKENS = {
    "what", "which", "my", "hurts", "treats", "medicine", "drug", "for", "with",
    "and", "is", "it", "true", "status", "of", "the", "provide", "give", "tell",
    "nafdac", "reg", "no", "genuine", "fake", "safe", "alcohol", "about",
}


def _looks_like_name(value: str) -> bool:
    if len(value) < 3 or len(value.split()) > 12:
        return False
    if not re.search(r"[A-Za-z]", value):
        return False
    # A bare number or a sentence is not a product name.
    if not re.search(r"[A-Za-z]{3}", value):
        return False
    tokens = set(re.findall(r"[a-z]+", value.lower()))
    if tokens & _NON_NAME_TOKENS:
        return False
    return True


def parse_message(text: str, known_names: Iterable[str] | None = None) -> MessageIntent:
    """Parse a message without contacting the backend or any model."""
    original = text or ""
    norm = normalize(original)
    reg = find_registration_number(original)
    medical = is_medical_question(original)

    candidate = norm
    if reg:
        candidate = candidate.replace(normalize(reg), " ")
    candidate = strip_filler(candidate)

    catalogue_hit = name_from_catalogue(candidate, known_names or ())
    if catalogue_hit:
        name = catalogue_hit
    elif medical or reg:
        # Do not turn a question or a phrase following a reg number into a name.
        name = None
    elif _looks_like_name(candidate):
        name = candidate
    else:
        name = None

    has_query = bool(reg or name)
    if medical:
        intent = "medical_question"
    elif has_query:
        intent = "lookup"
    else:
        intent = "clarify"

    notes: list[str] = []
    if reg:
        notes.append("registration number extracted first")
    if medical:
        notes.append("medical question detected; explanation must redirect")

    return MessageIntent(
        original=original,
        normalized=norm,
        registration_number=reg,
        name=name,
        intent=intent,
        medical_question=medical,
        needs_clarification=not has_query and not medical,
        extracted_by="deterministic" if has_query else "none",
        notes=notes,
    )