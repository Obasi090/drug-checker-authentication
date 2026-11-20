"""Offline verification facade for SMS and packaging observations.

This module is the only entry point the rest of the standalone component needs.
It composes the read-only catalogue, the common observation model, candidate
generation, field comparison and the six-way decision layer. It performs no
network calls, writes no data files and never uses OCR output as ground truth.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from .candidate import CandidateEvidence, CandidateSet, build_fuzzy_catalogue, generate_candidates
from .catalogue import DEFAULT_CATALOGUE_PATH, MedicineCatalogue, load_catalogue
from .decision import DecisionResult, VerificationStatus, decide
from .field_compare import FieldComparison, compare_fields
from .fuzzy import DrugCatalogue
from .observation import (
    MedicineObservation,
    observation_from_sms_text,
)
from .packaging import PACKAGE_RESULT_FIELDS, read_csv_rows
from .photo import PhotoResult

DEFAULT_PACKAGE_RESULTS = DEFAULT_CATALOGUE_PATH.parent / "packaging" / "package_results.csv"


class VerificationResult(BaseModel):
    """Complete internal verification outcome, separate from backend Findings."""

    model_config = ConfigDict(extra="forbid")

    observation_id: str
    source_channel: str
    status: VerificationStatus
    reasons: list[str] = Field(default_factory=list)
    status_explanation: str
    selected_product_id: str | None = None
    selected_candidate: CandidateEvidence | None = None
    candidates: CandidateSet
    field_comparisons: dict[str, list[FieldComparison]] = Field(default_factory=dict)
    review_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    accuracy_tested: bool = False
    catalogue_sha256: str
    notes: list[str] = Field(default_factory=list)

    @property
    def is_manual_review(self) -> bool:
        return self.status == "MANUAL_REVIEW_REQUIRED"


class VerificationEngine:
    """Composable, deterministic verification engine over the local catalogue."""

    def __init__(
        self,
        catalogue: MedicineCatalogue | None = None,
        *,
        catalogue_path: str | Path | None = None,
    ) -> None:
        if catalogue is not None and catalogue_path is not None:
            raise ValueError("pass either catalogue or catalogue_path, not both")
        self.catalogue = catalogue or load_catalogue(catalogue_path)
        self.fuzzy_catalogue: DrugCatalogue = build_fuzzy_catalogue(self.catalogue)

    def verify(self, observation: MedicineObservation) -> VerificationResult:
        candidate_set = generate_candidates(
            observation, self.catalogue, fuzzy_catalogue=self.fuzzy_catalogue
        )
        comparisons: dict[str, list[FieldComparison]] = {
            candidate.product.product_id: list(compare_fields(observation, candidate.product))
            for candidate in candidate_set.candidates
        }
        decision: DecisionResult = decide(observation, candidate_set, comparisons)
        selected = next(
            (
                candidate for candidate in candidate_set.candidates
                if candidate.product.product_id == decision.selected_product_id
            ),
            None,
        )

        notes = [
            "This local catalogue is a deterministic test catalogue, not an authoritative regulatory database.",
            "Fuzzy similarity scores are retrieval hints only, not identity measures.",
        ]
        if observation.source_channel != "sms":
            notes.append("OCR values are observations only; real-pack OCR accuracy remains NOT TESTED.")

        return VerificationResult(
            observation_id=observation.observation_id,
            source_channel=observation.source_channel,
            status=decision.status,
            reasons=decision.reasons,
            status_explanation=decision.status_explanation,
            selected_product_id=decision.selected_product_id,
            selected_candidate=selected,
            candidates=candidate_set,
            field_comparisons=comparisons,
            review_fields=decision.review_fields,
            missing_fields=decision.missing_fields,
            provenance=observation.provenance,
            accuracy_tested=False,
            catalogue_sha256=self.catalogue.source_sha256,
            notes=notes + list(observation.notes),
        )

    def verify_sms(
        self,
        text: str,
        *,
        known_names: Iterable[str] | None = None,
        observation_id: str = "SMS-1",
    ) -> VerificationResult:
        """Parse an SMS with the existing module, then verify the observation."""
        names = list(known_names) if known_names is not None else self.catalogue.brand_names
        observation = observation_from_sms_text(
            text, names, observation_id=observation_id
        )
        return self.verify(observation)

    def verify_photo_result(
        self,
        result: PhotoResult,
        *,
        observation_id: str = "PHOTO-1",
    ) -> VerificationResult:
        observation = MedicineObservation.from_photo_result(
            result, observation_id=observation_id
        )
        return self.verify(observation)

    def verify_package_row(
        self,
        row: Mapping[str, str],
        *,
        observation_id: str | None = None,
    ) -> VerificationResult:
        observation = MedicineObservation.from_package_result(
            dict(row), observation_id=observation_id
        )
        return self.verify(observation)

    def verify_package_results(
        self,
        path: str | Path | None = None,
    ) -> list[VerificationResult]:
        """Verify all reconciled packaging rows without writing to the CSV."""
        source = Path(path) if path is not None else DEFAULT_PACKAGE_RESULTS
        rows = read_csv_rows(source)
        missing = [name for name in PACKAGE_RESULT_FIELDS if rows and name not in rows[0]]
        if missing:
            raise ValueError(f"package results file is missing columns: {', '.join(missing)}")
        return [self.verify_package_row(row) for row in rows]


def verify_sms_text(
    text: str,
    *,
    catalogue: MedicineCatalogue | None = None,
    observation_id: str = "SMS-1",
) -> VerificationResult:
    """Convenience function for a one-off offline SMS verification."""
    return VerificationEngine(catalogue).verify_sms(text, observation_id=observation_id)
