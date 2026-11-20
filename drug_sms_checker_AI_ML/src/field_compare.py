"""Field-level comparison rules for the verification engine.

Every comparison keeps the observed and catalogue-side source text, assigns one
of five field statuses, and explains the result. No missing value is filled in;
no package volume is reinterpreted as strength; no fuzzy score is called a
confidence.

Field statuses: ``MATCH``, ``MISMATCH``, ``UNKNOWN``, ``UNPARSED``, ``CONFLICT``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict
from rapidfuzz import fuzz

from .catalogue import (
    CatalogueProduct,
    brand_key,
    derive_dosage_forms,
    generic_key,
    parse_strength_text,
    parse_volume_text,
    registration_key,
    strength_display,
    volume_display,
)
from .fuzzy import CUTOFF
from .observation import OBSERVED_FIELDS, MedicineObservation, ObservedField

FieldStatus = Literal["MATCH", "MISMATCH", "UNKNOWN", "UNPARSED", "CONFLICT"]


class FieldComparison(BaseModel):
    """One deterministic field comparison with preserved original values."""

    model_config = ConfigDict(extra="forbid")

    field: str
    status: FieldStatus
    observed_raw: str | None = None
    catalogue_raw: str | None = None
    observed_normalized: str | None = None
    catalogue_normalized: str | None = None
    reason: str
    similarity_score: float | None = None
    provenance: str = ""

    @property
    def is_negative_evidence(self) -> bool:
        return self.status in {"MISMATCH", "CONFLICT"}


def _observed(field: ObservedField) -> tuple[str | None, str]:
    if field.status == "CONFLICT":
        return None, "observed conflict"
    return field.value, field.provenance


def _missing_reason(field_name: str, field: ObservedField) -> str:
    if field.status == "CONFLICT":
        return f"{field_name} has conflicting observations and cannot be compared."
    if field.status == "NOT_VISIBLE":
        return f"{field_name} was not visible in the observation."
    return f"{field_name} was not supplied by the observation."


def _compare_registration(observation: MedicineObservation,
                          product: CatalogueProduct) -> FieldComparison:
    field = observation.field("registration_number")
    observed, provenance = _observed(field)
    catalogue = product.registration_number
    base = dict(
        field="registration_number",
        observed_raw=field.raw,
        catalogue_raw=catalogue,
        observed_normalized=registration_key(observed) or None,
        catalogue_normalized=product.registration_key,
        provenance=provenance,
    )
    if field.status == "CONFLICT":
        return FieldComparison(status="CONFLICT", reason=_missing_reason("Registration number", field), **base)
    if not field.usable or observed is None:
        return FieldComparison(status="UNKNOWN", reason=_missing_reason("Registration number", field), **base)
    if registration_key(observed) == product.registration_key:
        return FieldComparison(
            status="MATCH",
            reason=(
                f"Registration number {observed!r} exactly matches the catalogue value "
                f"after case and hyphen-glyph normalisation only."
            ),
            **base,
        )
    return FieldComparison(
        status="MISMATCH",
        reason=(
            f"Registration number {observed!r} differs from catalogue value "
            f"{catalogue!r}; registration numbers are never fuzzy-matched."
        ),
        **base,
    )


def _compare_brand(observation: MedicineObservation, product: CatalogueProduct) -> FieldComparison:
    field = observation.field("brand_name")
    observed, provenance = _observed(field)
    observed_key = brand_key(observed)
    catalogue_key = product.brand_key
    base = dict(
        field="brand_name",
        observed_raw=field.raw,
        catalogue_raw=product.brand_name,
        observed_normalized=observed_key or None,
        catalogue_normalized=catalogue_key or None,
        provenance=provenance,
    )
    if field.status == "CONFLICT":
        return FieldComparison(status="CONFLICT", reason=_missing_reason("Brand name", field), **base)
    if not field.usable or observed is None:
        return FieldComparison(status="UNKNOWN", reason=_missing_reason("Brand name", field), **base)
    if observed_key == catalogue_key:
        return FieldComparison(
            status="MATCH",
            reason="Brand names match after case, punctuation and whitespace normalisation.",
            **base,
        )
    score = round(float(fuzz.WRatio(observed_key, catalogue_key)), 1)
    return FieldComparison(
        status="MISMATCH",
        reason=(
            f"Brand name {observed!r} differs from catalogue value {product.brand_name!r}. "
            "similarity_score is supporting evidence only and cannot prove identity."
        ),
        similarity_score=score,
        **base,
    )


def _compare_generic(observation: MedicineObservation, product: CatalogueProduct) -> FieldComparison:
    field = observation.field("generic_name")
    observed, provenance = _observed(field)
    observed_key = generic_key(observed)
    catalogue_key = product.generic_key
    base = dict(
        field="generic_name",
        observed_raw=field.raw,
        catalogue_raw=product.generic_name,
        observed_normalized=observed_key or None,
        catalogue_normalized=catalogue_key or None,
        provenance=provenance,
    )
    if field.status == "CONFLICT":
        return FieldComparison(status="CONFLICT", reason=_missing_reason("Generic name", field), **base)
    if not field.usable or observed is None or not product.generic_name:
        reason = (
            _missing_reason("Generic name", field)
            if not field.usable or observed is None
            else "The catalogue row has no generic name to compare."
        )
        return FieldComparison(status="UNKNOWN", reason=reason, **base)
    if observed_key == catalogue_key:
        return FieldComparison(
            status="MATCH",
            reason=(
                "Generic names match as an ingredient set; repeated generics still "
                "require product disambiguation."
            ),
            **base,
        )
    return FieldComparison(
        status="MISMATCH",
        reason=f"Generic name {observed!r} differs from catalogue value {product.generic_name!r}.",
        **base,
    )


def _compare_manufacturer(observation: MedicineObservation,
                          product: CatalogueProduct) -> FieldComparison:
    field = observation.field("manufacturer")
    observed, provenance = _observed(field)
    catalogue = product.manufacturer
    base = dict(
        field="manufacturer",
        observed_raw=field.raw,
        catalogue_raw=catalogue,
        observed_normalized=brand_key(observed) or None,
        catalogue_normalized=brand_key(catalogue) or None,
        provenance=provenance,
    )
    if field.status == "CONFLICT":
        return FieldComparison(status="CONFLICT", reason=_missing_reason("Manufacturer", field), **base)
    if not field.usable or observed is None:
        return FieldComparison(status="UNKNOWN", reason=_missing_reason("Manufacturer", field), **base)
    if catalogue is None:
        return FieldComparison(
            status="UNKNOWN",
            reason=(
                "The catalogue manufacturer is blank. applicant_name is never used "
                "as a manufacturer substitute."
            ),
            **base,
        )
    if brand_key(observed) == brand_key(catalogue):
        return FieldComparison(
            status="MATCH",
            reason="Manufacturer names match after conservative normalisation.",
            **base,
        )
    return FieldComparison(
        status="MISMATCH",
        reason=f"Manufacturer {observed!r} differs from catalogue value {catalogue!r}.",
        **base,
    )


def _strength_signature(parsed: object) -> tuple[tuple[str, str], ...]:
    return tuple(
        (component.base_value, component.base_unit)
        for component in parsed.components  # type: ignore[attr-defined]
    )


def _compare_strength(observation: MedicineObservation, product: CatalogueProduct) -> FieldComparison:
    field = observation.field("strength")
    observed, provenance = _observed(field)
    catalogue_parsed = parse_strength_text(product.brand_name)
    observed_parsed = parse_strength_text(observed)
    base = dict(
        field="strength",
        observed_raw=field.raw,
        catalogue_raw=product.brand_name,
        observed_normalized=strength_display(observed_parsed),
        catalogue_normalized=strength_display(catalogue_parsed),
        provenance=provenance or "catalogue strength derived from brand_name",
    )
    if field.status == "CONFLICT":
        return FieldComparison(status="CONFLICT", reason=_missing_reason("Strength", field), **base)
    if not field.usable or observed is None:
        return FieldComparison(status="UNKNOWN", reason=_missing_reason("Strength", field), **base)
    if not catalogue_parsed.parsed:
        return FieldComparison(
            status="UNKNOWN",
            reason="The catalogue brand text has no parseable numeric strength with an explicit unit.",
            **base,
        )
    if not observed_parsed.parsed:
        return FieldComparison(
            status="UNPARSED",
            reason=(
                f"Observed strength {observed!r} has no parseable numeric value with an "
                "explicit strength unit; package volume cannot be used as strength."
            ),
            **base,
        )
    if _strength_signature(observed_parsed) == _strength_signature(catalogue_parsed):
        return FieldComparison(
            status="MATCH",
            reason="Strength components match numerically after explicit-unit normalisation.",
            **base,
        )
    return FieldComparison(
        status="MISMATCH",
        reason=(
            f"Observed strength {strength_display(observed_parsed)!r} differs from "
            f"catalogue-derived strength {strength_display(catalogue_parsed)!r}."
        ),
        **base,
    )


def _derive_forms(value: str | None) -> tuple[str, ...]:
    return derive_dosage_forms(value)


def _compare_dosage_form(observation: MedicineObservation,
                         product: CatalogueProduct) -> FieldComparison:
    field = observation.field("dosage_form")
    explicit = field.usable
    source_text = field.value if explicit else observation.field("brand_name").value
    observed_forms = _derive_forms(source_text)
    catalogue_forms = _derive_forms(product.brand_name)
    base = dict(
        field="dosage_form",
        observed_raw=field.raw if explicit else source_text,
        catalogue_raw=product.brand_name,
        observed_normalized=", ".join(observed_forms) or None,
        catalogue_normalized=", ".join(catalogue_forms) or None,
        provenance=field.provenance or (
            "derived from observed brand_name" if source_text else ""
        ),
    )
    if field.status == "CONFLICT":
        return FieldComparison(status="CONFLICT", reason=_missing_reason("Dosage form", field), **base)
    if explicit and not observed_forms:
        return FieldComparison(
            status="UNPARSED",
            reason=f"Observed dosage form {field.value!r} does not contain a supported form token.",
            **base,
        )
    if not observed_forms or not catalogue_forms:
        return FieldComparison(
            status="UNKNOWN",
            reason="One or both sides have no supported dosage-form token.",
            **base,
        )
    if set(observed_forms) == set(catalogue_forms):
        return FieldComparison(
            status="MATCH",
            reason="Dosage-form tokens match from explicitly present text.",
            **base,
        )
    return FieldComparison(
        status="MISMATCH",
        reason=(
            f"Observed dosage form {', '.join(observed_forms)!r} differs from "
            f"catalogue-derived form {', '.join(catalogue_forms)!r}."
        ),
        **base,
    )


def _volume_signature(parsed: object) -> tuple[tuple[str, str], ...]:
    return tuple(
        (component.base_value_ml, "ml")
        for component in parsed.components  # type: ignore[attr-defined]
    )


def _compare_package_volume(observation: MedicineObservation,
                            product: CatalogueProduct) -> FieldComparison:
    field = observation.field("package_volume")
    observed, provenance = _observed(field)
    catalogue_parsed = parse_volume_text(product.brand_name)
    observed_parsed = parse_volume_text(observed)
    base = dict(
        field="package_volume",
        observed_raw=field.raw,
        catalogue_raw=product.brand_name,
        observed_normalized=volume_display(observed_parsed),
        catalogue_normalized=volume_display(catalogue_parsed),
        provenance=provenance or "catalogue volume derived from brand_name",
    )
    if field.status == "CONFLICT":
        return FieldComparison(status="CONFLICT", reason=_missing_reason("Package volume", field), **base)
    if not field.usable or observed is None:
        return FieldComparison(status="UNKNOWN", reason=_missing_reason("Package volume", field), **base)
    if not catalogue_parsed.parsed:
        return FieldComparison(
            status="UNKNOWN",
            reason="The catalogue brand text has no parseable package volume.",
            **base,
        )
    if not observed_parsed.parsed:
        return FieldComparison(
            status="UNPARSED",
            reason=f"Observed package volume {observed!r} has no parseable value with an explicit unit.",
            **base,
        )
    if _volume_signature(observed_parsed) == _volume_signature(catalogue_parsed):
        return FieldComparison(
            status="MATCH",
            reason="Package volumes match in millilitres; volume is never compared as strength.",
            **base,
        )
    return FieldComparison(
        status="MISMATCH",
        reason=(
            f"Observed package volume {volume_display(observed_parsed)!r} differs from "
            f"catalogue-derived volume {volume_display(catalogue_parsed)!r}."
        ),
        **base,
    )


_COMPARATORS = {
    "registration_number": _compare_registration,
    "brand_name": _compare_brand,
    "generic_name": _compare_generic,
    "manufacturer": _compare_manufacturer,
    "strength": _compare_strength,
    "dosage_form": _compare_dosage_form,
    "package_volume": _compare_package_volume,
}


def compare_fields(observation: MedicineObservation,
                   product: CatalogueProduct) -> tuple[FieldComparison, ...]:
    """Compare all seven required fields in a stable order."""
    return tuple(_COMPARATORS[name](observation, product) for name in OBSERVED_FIELDS)


def comparisons_by_field(
    comparisons: list[FieldComparison] | tuple[FieldComparison, ...]
) -> dict[str, FieldComparison]:
    return {item.field: item for item in comparisons}
