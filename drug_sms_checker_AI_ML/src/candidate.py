"""Explainable candidate generation for the verification engine.

This module deliberately separates *retrieval evidence* from a verification
decision. A fuzzy hit is a suggestion only: it carries a ``similarity_score``,
never a probability or confidence, and always requires confirmation.

Retrieval priority:

1. exact registration number,
2. exact brand name,
3. exact generic name (all matching products are preserved),
4. fuzzy brand/generic suggestions from the existing ``src.fuzzy`` policy.

Fuzzy suggestions are suppressed when a registration number is present but does
not exactly match the catalogue, so an unknown number can never become a fuzzy
name guess.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .catalogue import CatalogueProduct, MedicineCatalogue, registration_key
from .fuzzy import CatalogueEntry, DrugCatalogue, suggest
from .observation import MedicineObservation

MatchMethod = Literal[
    "registration_number_exact",
    "brand_name_exact",
    "generic_name_exact",
    "fuzzy_brand_name",
    "fuzzy_generic_name",
]

PATH_PRIORITY: dict[str, int] = {
    "registration_number_exact": 0,
    "brand_name_exact": 1,
    "generic_name_exact": 2,
    "fuzzy_brand_name": 3,
    "fuzzy_generic_name": 4,
}

PATH_LABELS: dict[str, str] = {
    "registration_number_exact": "exact registration number",
    "brand_name_exact": "exact brand name",
    "generic_name_exact": "exact generic name",
    "fuzzy_brand_name": "fuzzy brand-name suggestion",
    "fuzzy_generic_name": "fuzzy generic-name suggestion",
}


class CandidateEvidence(BaseModel):
    """One catalogue product and every retrieval path that found it."""

    model_config = ConfigDict(extra="forbid")

    product: CatalogueProduct
    matched_by: MatchMethod
    matched_paths: list[MatchMethod] = Field(default_factory=list)
    matched_values: list[str] = Field(default_factory=list)
    similarity_score: float | None = None
    requires_confirmation: bool = True
    reasons: list[str] = Field(default_factory=list)

    @property
    def identity_label(self) -> str:
        return self.product.identity_label

    @property
    def is_registration_exact(self) -> bool:
        return "registration_number_exact" in self.matched_paths

    @property
    def is_fuzzy_only(self) -> bool:
        return all(path.startswith("fuzzy_") for path in self.matched_paths)


class CandidateSet(BaseModel):
    """Deterministically ranked candidates plus retrieval metadata."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[CandidateEvidence] = Field(default_factory=list)
    exact_registration_product_id: str | None = None
    fuzzy_suggestions_used: bool = False
    ambiguous: bool = False
    requires_confirmation: bool = False
    reasons: list[str] = Field(default_factory=list)
    search_summary: dict[str, int] = Field(default_factory=dict)

    @property
    def selected(self) -> CandidateEvidence | None:
        return self.candidates[0] if self.candidates else None


def build_fuzzy_catalogue(catalogue: MedicineCatalogue) -> DrugCatalogue:
    """Adapt the read-only catalogue into the existing suggestion engine."""
    return DrugCatalogue([
        CatalogueEntry(
            brand_name=product.brand_name,
            generic_name=product.generic_name or "",
            registration_number=product.registration_number,
            applicant_name=product.applicant_name or "",
            manufacturer=product.manufacturer or "",
            source_url=product.source_url or "",
        )
        for product in catalogue.products
    ])


def _product_for_suggestion(
    catalogue: MedicineCatalogue,
    registration_number: str,
) -> CatalogueProduct | None:
    """Resolve a fuzzy suggestion to a catalogue product without fuzzy NRNs."""
    return catalogue.registration_lookup(registration_number)


def generate_candidates(
    observation: MedicineObservation,
    catalogue: MedicineCatalogue,
    *,
    fuzzy_catalogue: DrugCatalogue | None = None,
    limit: int = 5,
) -> CandidateSet:
    """Return ranked candidates. No verification decision is made here."""
    reasons: list[str] = []
    summary: dict[str, int] = {
        "registration_number_exact": 0,
        "brand_name_exact": 0,
        "generic_name_exact": 0,
        "fuzzy_brand_name": 0,
        "fuzzy_generic_name": 0,
    }

    # Mutable accumulator: path evidence is merged before immutable models are built.
    pending: dict[str, dict[str, object]] = {}

    def add(
        product: CatalogueProduct,
        path: MatchMethod,
        matched_value: str,
        *,
        similarity_score: float | None = None,
        requires_confirmation: bool,
        reason: str,
    ) -> None:
        entry = pending.setdefault(product.product_id, {
            "product": product,
            "paths": [],
            "values": [],
            "best_score": None,
            "confirm": False,
            "reasons": [],
        })
        paths = entry["paths"]
        values = entry["values"]
        entry_reasons = entry["reasons"]
        assert isinstance(paths, list) and isinstance(values, list) and isinstance(entry_reasons, list)

        if path not in paths:
            paths.append(path)
            summary[path] += 1
        if matched_value not in values:
            values.append(matched_value)
        if similarity_score is not None:
            best = entry["best_score"]
            if best is None or similarity_score > float(best):
                entry["best_score"] = similarity_score
        if requires_confirmation:
            entry["confirm"] = True
        if reason not in entry_reasons:
            entry_reasons.append(reason)

    reg_field = observation.field("registration_number")
    brand_field = observation.field("brand_name")
    generic_field = observation.field("generic_name")

    registration_present = reg_field.usable and reg_field.value is not None
    registration_product: CatalogueProduct | None = None
    if registration_present and reg_field.value is not None:
        registration_product = catalogue.registration_lookup(reg_field.value)
        if registration_product is not None:
            add(
                registration_product,
                "registration_number_exact",
                reg_field.value,
                requires_confirmation=False,
                reason=(
                    f"Registration number {reg_field.value!r} exactly matches "
                    f"{registration_product.identity_label!r}."
                ),
            )
            reasons.append(
                "Exact registration-number lookup was prioritised; fuzzy name "
                "suggestions were not used for this observation."
            )
        else:
            reasons.append(
                f"Registration number {reg_field.value!r} has no exact catalogue entry; "
                "fuzzy name suggestions are suppressed for this observation."
            )

    exact_brands: list[CatalogueProduct] = []
    if brand_field.usable and brand_field.value is not None:
        exact_brands = catalogue.brand_lookup(brand_field.value)
        brand_confirmation = len(exact_brands) != 1
        for product in exact_brands:
            add(
                product,
                "brand_name_exact",
                brand_field.value,
                requires_confirmation=brand_confirmation,
                reason=(
                    f"Brand name {brand_field.value!r} exactly matches "
                    f"{product.identity_label!r} after conservative normalisation."
                ),
            )
        if len(exact_brands) > 1:
            reasons.append(
                f"The exact brand name returned {len(exact_brands)} products; "
                "all are retained for disambiguation."
            )

    # SMS adapters have one name field. If that text is an exact generic name,
    # preserve every matching product rather than collapsing to one brand.
    brand_generic_matches: list[CatalogueProduct] = []
    if brand_field.usable and brand_field.value is not None and not exact_brands:
        brand_generic_matches = catalogue.generic_lookup(brand_field.value)
        for product in brand_generic_matches:
            add(
                product,
                "generic_name_exact",
                brand_field.value,
                requires_confirmation=True,
                reason=(
                    f"Supplied name {brand_field.value!r} exactly matches the generic name "
                    f"of {product.identity_label!r}; generic names can collide."
                ),
            )
        if len(brand_generic_matches) > 1:
            reasons.append(
                f"The supplied name is an exact generic name for {len(brand_generic_matches)} "
                "products; no first-row selection was made."
            )

    exact_generics: list[CatalogueProduct] = []
    if generic_field.usable and generic_field.value is not None:
        exact_generics = catalogue.generic_lookup(generic_field.value)
        for product in exact_generics:
            add(
                product,
                "generic_name_exact",
                generic_field.value,
                requires_confirmation=True,
                reason=(
                    f"Generic name {generic_field.value!r} exactly matches "
                    f"{product.identity_label!r}; generic names can collide."
                ),
            )
        if len(exact_generics) > 1:
            reasons.append(
                f"The exact generic name returned {len(exact_generics)} products; "
                "no first-row selection was made."
            )

    fuzzy_used = False
    ambiguous = False
    if not registration_present and (brand_field.usable or generic_field.usable):
        engine = fuzzy_catalogue or build_fuzzy_catalogue(catalogue)

        if (brand_field.usable and brand_field.value is not None
                and not exact_brands and not brand_generic_matches):
            fuzzy_used = True
            suggestion = suggest(brand_field.value, engine, limit=limit)
            ambiguous = ambiguous or suggestion.status == "ambiguous"
            for item in suggestion.candidates:
                product = _product_for_suggestion(catalogue, item.registration_number)
                if product is None:
                    continue
                add(
                    product,
                    "fuzzy_brand_name",
                    item.value,
                    similarity_score=float(item.score),
                    requires_confirmation=True,
                    reason=(
                        f"Brand text is similar to {product.identity_label!r} "
                        f"(similarity_score={item.score:.1f}); this is a suggestion only."
                    ),
                )

        if generic_field.usable and generic_field.value is not None and not exact_generics:
            fuzzy_used = True
            suggestion = suggest(generic_field.value, engine, limit=limit)
            ambiguous = ambiguous or suggestion.status == "ambiguous"
            for item in suggestion.candidates:
                product = _product_for_suggestion(catalogue, item.registration_number)
                if product is None:
                    continue
                add(
                    product,
                    "fuzzy_generic_name",
                    item.value,
                    similarity_score=float(item.score),
                    requires_confirmation=True,
                    reason=(
                        f"Generic text is similar to {product.identity_label!r} "
                        f"(similarity_score={item.score:.1f}); this is a suggestion only."
                    ),
                )

    candidates: list[CandidateEvidence] = []
    for product_id, entry in pending.items():
        product = entry["product"]
        assert isinstance(product, CatalogueProduct)
        paths_raw = entry["paths"]
        values_raw = entry["values"]
        reasons_raw = entry["reasons"]
        assert isinstance(paths_raw, list) and isinstance(values_raw, list) and isinstance(reasons_raw, list)
        paths = [str(path) for path in paths_raw]
        primary = min(paths, key=lambda path: PATH_PRIORITY[path])
        candidates.append(CandidateEvidence(
            product=product,
            matched_by=primary,  # type: ignore[arg-type]
            matched_paths=paths,  # type: ignore[arg-type]
            matched_values=[str(value) for value in values_raw],
            similarity_score=(
                float(entry["best_score"]) if entry["best_score"] is not None else None
            ),
            requires_confirmation=bool(entry["confirm"]),
            reasons=[str(reason) for reason in reasons_raw],
        ))

    candidates.sort(key=lambda item: (
        PATH_PRIORITY[item.matched_by],
        -((item.similarity_score or 0.0)),
        item.product.row_number,
    ))

    if not candidates:
        reasons.append("No catalogued product was retrieved from the usable observation fields.")
    if fuzzy_used:
        reasons.append("Fuzzy suggestions were generated; their similarity scores are retrieval hints only.")

    return CandidateSet(
        candidates=candidates,
        exact_registration_product_id=(
            registration_product.product_id if registration_product is not None else None
        ),
        fuzzy_suggestions_used=fuzzy_used,
        ambiguous=ambiguous or len(candidates) > 1,
        requires_confirmation=any(item.requires_confirmation for item in candidates),
        reasons=reasons,
        search_summary=summary,
    )


def registration_lookup_only(
    value: str | None, catalogue: MedicineCatalogue
) -> CatalogueProduct | None:
    """Small helper for callers that need exact NRN lookup without suggestions."""
    if not value or not registration_key(value):
        return None
    return catalogue.registration_lookup(value)
