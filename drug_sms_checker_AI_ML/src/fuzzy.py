"""Spelling forgiveness over the approved catalogue.

Exact matches win. Fuzzy matches never auto-substitute a medicine: they always
require explicit user confirmation (and short or close calls require a choice).
Cutoffs below are starting values that must be justified by tests, not guessed
at demo time.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Literal

from rapidfuzz import fuzz, process
from pydantic import BaseModel, ConfigDict

from .message import normalize

# Calibrated against tests/test_fuzzy.py. Do not lower without re-running them.
CUTOFF = 72
AMBIGUOUS_GAP = 6
SHORT_NAME_LENGTH = 5


class CatalogueEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    brand_name: str
    generic_name: str = ""
    registration_number: str = ""
    applicant_name: str = ""
    manufacturer: str = ""
    source_url: str = ""


class DrugCatalogue:
    """Read-only view of the approved catalogue CSV. No writes, no network."""

    def __init__(self, entries: list[CatalogueEntry]) -> None:
        self.entries = entries
        self._aliases: list[tuple[str, str, CatalogueEntry]] = []
        for entry in entries:
            for value, field in ((entry.brand_name, "brand_name"), (entry.generic_name, "generic_name")):
                if value and value.lower() != "not visible":
                    self._aliases.append((normalize(value), field, entry))

    @classmethod
    def from_csv(cls, path: str | Path) -> "DrugCatalogue":
        with Path(path).open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        return cls([CatalogueEntry.model_validate(row) for row in rows])

    def alias_values(self) -> list[str]:
        return [value for value, _, _ in self._aliases]

    def entry_for_alias(self, value: str) -> tuple[str, CatalogueEntry] | None:
        for alias, field, entry in self._aliases:
            if alias == value:
                return field, entry
        return None


class Candidate(BaseModel):
    value: str
    matched_field: str
    score: float
    brand_name: str
    registration_number: str
    source_url: str


class Suggestion(BaseModel):
    status: Literal["exact", "suggest", "ambiguous", "clarify", "empty_catalogue"]
    candidates: list[Candidate] = []
    requires_confirmation: bool = True
    prompt: str = ""


def distinctive_tokens(value: str) -> set[str]:
    """Tokens long enough to identify a product, excluding 2-3 digit numbers."""
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    return {
        t for t in tokens
        if (len(t) >= 4) or (len(t) == 3 and not t.isdigit())
    }


def suggest(query: str, catalogue: DrugCatalogue, limit: int = 5) -> Suggestion:
    q = normalize(query)
    if not q:
        return Suggestion(status="clarify", prompt="Please send the name printed on the pack.")
    if not catalogue.alias_values():
        return Suggestion(status="empty_catalogue", prompt="No approved catalogue is available.")

    for alias, field, entry in catalogue._aliases:
        if alias == q:
            return Suggestion(
                status="exact",
                candidates=[Candidate(value=alias, matched_field=field, score=100.0,
                                      brand_name=entry.brand_name,
                                      registration_number=entry.registration_number,
                                      source_url=entry.source_url)],
                requires_confirmation=False,
            )

    # WRatio alone over-rewards shared dosage/form tokens ("150 mg capsules").
    # Gate on a distinctive token so a similarly-shaped but different product
    # cannot become the top suggestion.
    query_tokens = distinctive_tokens(q)
    aliases = catalogue.alias_values()
    if query_tokens:
        aliases = [a for a in aliases if query_tokens & distinctive_tokens(a)]
    if not aliases:
        return Suggestion(status="clarify", prompt="We could not match that name. Please send the name or number printed on the pack.")

    hits = process.extract(q, aliases, scorer=fuzz.WRatio, limit=limit)
    hits = [(value, score) for value, score, _ in hits if score >= CUTOFF]
    if not hits:
        return Suggestion(status="clarify", prompt="We could not match that name. Please send the name or number printed on the pack.")

    candidates: list[Candidate] = []
    seen: set[tuple[str, str]] = set()
    for value, score in hits:
        found = catalogue.entry_for_alias(value)
        if not found:
            continue
        field, entry = found
        key = (entry.brand_name, entry.registration_number)
        if key in seen:
            continue
        seen.add(key)
        candidates.append(Candidate(value=value, matched_field=field, score=round(float(score), 1),
                                    brand_name=entry.brand_name,
                                    registration_number=entry.registration_number,
                                    source_url=entry.source_url))

    if not candidates:
        return Suggestion(status="clarify", prompt="We could not match that name. Please send the name or number printed on the pack.")

    short = len(q.replace(" ", "")) < SHORT_NAME_LENGTH
    close = len(candidates) > 1 and candidates[0].score - candidates[1].score < AMBIGUOUS_GAP
    if short or close:
        options = "; ".join(c.brand_name for c in candidates[:3])
        return Suggestion(status="ambiguous", candidates=candidates[:3],
                          prompt=f"Please choose the product you mean: {options}.")

    return Suggestion(status="suggest", candidates=candidates[:3], requires_confirmation=True,
                      prompt=f"Did you mean {candidates[0].brand_name}? Reply YES to check or choose from the list.")
