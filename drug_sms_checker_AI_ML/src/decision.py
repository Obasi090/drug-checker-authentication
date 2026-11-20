"""Six-way verification decision layer.

The only decision statuses are ``MATCH``, ``PARTIAL_MATCH``, ``MISMATCH``,
``NO_MATCH``, ``INSUFFICIENT_INFORMATION`` and ``MANUAL_REVIEW_REQUIRED``.
This module emits human-readable reasons and never produces a confidence score,
probability or percentage.

Key distinctions:

- ``NO_MATCH``: enough searchable evidence was supplied, but nothing was found.
- ``INSUFFICIENT_INFORMATION``: too little evidence was supplied to search or decide.
- ``MISMATCH``: a product was identified, but an observed field directly conflicts.
- ``PARTIAL_MATCH``: one plausible product, with incomplete or weak support.
- ``MANUAL_REVIEW_REQUIRED``: conflicts, ambiguity or unconfirmed suggestions.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .candidate import CandidateSet
from .fuzzy import CUTOFF
from .field_compare import FieldComparison, comparisons_by_field
from .observation import MedicineObservation

VerificationStatus = Literal[
    "MATCH",
    "PARTIAL_MATCH",
    "MISMATCH",
    "NO_MATCH",
    "INSUFFICIENT_INFORMATION",
    "MANUAL_REVIEW_REQUIRED",
]

VERIFICATION_STATUSES: tuple[str, ...] = (
    "MATCH",
    "PARTIAL_MATCH",
    "MISMATCH",
    "NO_MATCH",
    "INSUFFICIENT_INFORMATION",
    "MANUAL_REVIEW_REQUIRED",
)

STATUS_EXPLANATIONS: dict[str, str] = {
    "MATCH": "One unique candidate is supported by exact evidence and has no conflicting fields.",
    "PARTIAL_MATCH": "One plausible candidate was found, but some supporting evidence is missing or weak.",
    "MISMATCH": "A candidate was identified, but at least one observed field directly conflicts.",
    "NO_MATCH": "The observation was sufficient to search, but no catalogue candidate was found.",
    "INSUFFICIENT_INFORMATION": "Too few usable fields were supplied to identify or exclude a product.",
    "MANUAL_REVIEW_REQUIRED": "A conflict, ambiguity or unconfirmed suggestion requires human review.",
}

FIELD_LABELS: dict[str, str] = {
    "brand_name": "brand name",
    "generic_name": "generic name",
    "registration_number": "registration number",
    "manufacturer": "manufacturer",
    "strength": "strength",
    "dosage_form": "dosage form",
    "package_volume": "package volume",
}

# Dosage form is intentionally excluded: in this catalogue it is derived from
# the same brand text used for candidate generation, so it is not independent.
CORROBORATING_FIELDS = ("generic_name", "manufacturer", "strength")


class DecisionResult(BaseModel):
    """Internal decision plus the evidence used to reach it."""

    model_config = ConfigDict(extra="forbid")

    status: VerificationStatus
    reasons: list[str] = Field(default_factory=list)
    status_explanation: str
    selected_product_id: str | None = None
    review_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)


def _label(name: str) -> str:
    return FIELD_LABELS.get(name, name)


def _result(
    status: VerificationStatus,
    reasons: list[str],
    *,
    selected_product_id: str | None = None,
    review_fields: list[str] | None = None,
    missing_fields: list[str] | None = None,
) -> DecisionResult:
    # Preserve order without duplicate reasons.
    unique_reasons = list(dict.fromkeys(reasons))
    return DecisionResult(
        status=status,
        reasons=unique_reasons,
        status_explanation=STATUS_EXPLANATIONS[status],
        selected_product_id=selected_product_id,
        review_fields=list(dict.fromkeys(review_fields or [])),
        missing_fields=list(dict.fromkeys(missing_fields or [])),
    )


def _source_conflict_reasons(observation: MedicineObservation) -> list[str]:
    reasons: list[str] = []
    for field_name in observation.conflict_fields():
        field = observation.field(field_name)
        reasons.append(
            f"The {_label(field_name)} observation contains a genuine conflict; "
            f"both original values were retained: {field.raw!r}."
        )
    if observation.source_manual_review_required and not observation.conflict_fields():
        flagged = ", ".join(_label(name) for name in observation.source_manual_review_fields)
        reasons.append(
            f"The source already requires manual review for: {flagged or 'unspecified fields'}."
        )
    return reasons


def decide(
    observation: MedicineObservation,
    candidates: CandidateSet,
    comparisons: dict[str, tuple[FieldComparison, ...] | list[FieldComparison]],
) -> DecisionResult:
    """Apply the deterministic six-way decision policy."""
    conflict_reasons = _source_conflict_reasons(observation)
    review_fields = list(observation.conflict_fields())
    if observation.source_manual_review_fields:
        review_fields.extend(observation.source_manual_review_fields)

    if conflict_reasons:
        return _result(
            "MANUAL_REVIEW_REQUIRED",
            conflict_reasons + ["OCR or source conflicts are observations only and cannot be resolved automatically."],
            selected_product_id=candidates.selected.product.product_id if candidates.selected else None,
            review_fields=review_fields,
        )

    searchable = observation.searchable_fields()
    if not searchable:
        present = observation.present_fields()
        detail = (
            f"Usable but non-identifying fields were supplied: {', '.join(_label(n) for n in present)}."
            if present else "No usable identity fields were supplied."
        )
        return _result(
            "INSUFFICIENT_INFORMATION",
            [
                "The observation has no usable registration number, brand name or generic name.",
                detail,
                "Strength, dosage form and package volume alone cannot identify or exclude a product.",
            ],
            review_fields=review_fields,
        )

    if not candidates.candidates:
        searched = ", ".join(
            f"{_label(name)}={observation.field(name).value!r}" for name in searchable
        )
        return _result(
            "NO_MATCH",
            [
                f"Sufficient searchable evidence was supplied ({searched}), "
                "but no catalogue candidate was found.",
                "Fuzzy similarity was not promoted to a match.",
            ],
            review_fields=review_fields,
        )

    selected = candidates.selected
    assert selected is not None
    reg_selected = candidates.exact_registration_product_id == selected.product.product_id
    selection_reasons: list[str] = []
    if reg_selected:
        selection_reasons.append(
            f"Registration number {observation.field('registration_number').value!r} exactly "
            f"selected {selected.identity_label!r}."
        )
        if len(candidates.candidates) > 1:
            selection_reasons.append(
                "Other name-based candidates were retained for transparency but were not "
                "used because exact registration-number lookup takes priority."
            )
    elif len(candidates.candidates) > 1:
        return _result(
            "MANUAL_REVIEW_REQUIRED",
            [
                f"{len(candidates.candidates)} catalogue products were retrieved without an "
                "exact registration number; all candidates were retained.",
                "A human must disambiguate these products; no first candidate was accepted.",
            ],
            review_fields=review_fields,
        )
    else:
        selection_reasons.append(
            f"One candidate was retrieved by {selected.matched_by.replace('_', ' ')}: "
            f"{selected.identity_label!r}."
        )

    field_rows = comparisons.get(selected.product.product_id, ())
    by_field = comparisons_by_field(field_rows)
    missing_fields = [
        item.field for item in field_rows if item.status == "UNKNOWN" and item.provenance == ""
    ]
    if not missing_fields:
        missing_fields = [
            item.field for item in field_rows
            if item.status == "UNKNOWN" and "was not supplied" in item.reason
        ]
    for item in field_rows:
        if item.status in {"MISMATCH", "UNPARSED", "CONFLICT"}:
            review_fields.append(item.field)

    conflict_rows = [item for item in field_rows if item.status == "CONFLICT"]
    if conflict_rows:
        return _result(
            "MANUAL_REVIEW_REQUIRED",
            selection_reasons + [
                f"{_label(item.field)} could not be compared because the observation conflicts: "
                f"{item.reason}"
                for item in conflict_rows
            ],
            selected_product_id=selected.product.product_id,
            review_fields=review_fields,
            missing_fields=missing_fields,
        )

    if not reg_selected and selected.requires_confirmation:
        basis = (
            "a fuzzy suggestion" if selected.is_fuzzy_only
            else "an exact generic-name match with colliding products"
        )
        return _result(
            "MANUAL_REVIEW_REQUIRED",
            selection_reasons + [
                f"This candidate came from {basis} and requires explicit confirmation "
                "before any verification result is accepted.",
                "Similarity was not accepted as identity evidence.",
            ],
            selected_product_id=selected.product.product_id,
            review_fields=review_fields,
            missing_fields=missing_fields,
        )

    mismatches = [item for item in field_rows if item.status == "MISMATCH"]
    brand = by_field.get("brand_name")
    soft_brand_mismatch = (
        reg_selected
        and brand is not None
        and brand.status == "MISMATCH"
        and brand.similarity_score is not None
        and brand.similarity_score >= CUTOFF
    )
    hard_mismatches = [
        item for item in mismatches if not (soft_brand_mismatch and item.field == "brand_name")
    ]

    if hard_mismatches:
        return _result(
            "MISMATCH",
            selection_reasons + [
                f"{_label(item.field)} conflicts: {item.reason}" for item in hard_mismatches
            ],
            selected_product_id=selected.product.product_id,
            review_fields=review_fields,
            missing_fields=missing_fields,
        )

    if soft_brand_mismatch and brand is not None:
        return _result(
            "PARTIAL_MATCH",
            selection_reasons + [
                "The registration number matches exactly, but the observed brand text only "
                f"resembles the catalogue brand (similarity_score={brand.similarity_score:.1f}).",
                "Brand similarity is a suggestion, not proof of identity; confirmation is required.",
            ],
            selected_product_id=selected.product.product_id,
            review_fields=review_fields,
            missing_fields=missing_fields,
        )

    unparsed = [item for item in field_rows if item.status == "UNPARSED"]
    if unparsed:
        return _result(
            "MANUAL_REVIEW_REQUIRED",
            selection_reasons + [
                f"{_label(item.field)} is present but could not be parsed safely: {item.reason}"
                for item in unparsed
            ],
            selected_product_id=selected.product.product_id,
            review_fields=review_fields,
            missing_fields=missing_fields,
        )

    if reg_selected:
        reasons = selection_reasons + [
            "All comparable fields are consistent with the registration-number match."
        ]
        if missing_fields:
            reasons.append(
                "Some supporting fields were not supplied and remain unknown: "
                + ", ".join(_label(name) for name in missing_fields)
                + "."
            )
        return _result(
            "MATCH",
            reasons,
            selected_product_id=selected.product.product_id,
            review_fields=review_fields,
            missing_fields=missing_fields,
        )

    corroborating = [
        item.field for item in field_rows
        if item.status == "MATCH" and item.field in CORROBORATING_FIELDS
    ]
    if corroborating:
        return _result(
            "MATCH",
            selection_reasons + [
                "The exact brand-name candidate is independently corroborated by: "
                + ", ".join(_label(name) for name in corroborating)
                + ".",
                "No conflicting fields were observed.",
            ],
            selected_product_id=selected.product.product_id,
            review_fields=review_fields,
            missing_fields=missing_fields,
        )

    return _result(
        "PARTIAL_MATCH",
        selection_reasons + [
            "The candidate is plausible but rests on name evidence alone; no independent "
            "supporting field was available.",
            "Registration number, generic name, manufacturer and strength remain unknown "
            "unless separately supplied.",
        ],
        selected_product_id=selected.product.product_id,
        review_fields=review_fields,
        missing_fields=missing_fields,
    )
