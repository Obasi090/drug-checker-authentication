"""Shared data contracts between the drug-checking backend and AI layer.

These models describe registry and regulatory findings. They do not establish
whether a medicine or physical pack is safe, genuine, or counterfeit.
"""

from __future__ import annotations

from typing import Any, Callable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError


# Keep this True until the backend owner confirms that the proposed contract
# is the authoritative interface used by every caller.
AWAITING_BACKEND_CONFIRMATION = True


Status = Literal["found", "multiple", "not_found", "invalid"]
QueryType = Literal["name", "reg_number"]
AlertType = Literal["recalled", "suspended", "withdrawn", "cancelled", "warning"]
AlertMatchType = Literal["reg_number", "name", "registration_number", "brand_name", "generic_name", "source_link"]


class ContractError(ValueError):
    """Raised when backend findings do not satisfy the shared contract."""


class _OpenModel(BaseModel):
    """Allow forward-compatible backend fields while validating known ones."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class DrugMatch(_OpenModel):
    """One product row returned from the Greenbook registry."""

    product_id: int | None = None
    reg_number: str | None = None
    brand_name: str
    generic_name: str | None = None
    manufacturer: str | None = None
    applicant: str | None = None
    strength: str | None = None
    dosage_form: str | None = None
    pack_size: str | None = None
    category: str | None = None
    marketing_category: str | None = None
    registry_status: str | None = None
    approved_at: str | None = None
    expires_at: str | None = None
    detail_url: str | None = None
    data_quality_note: str | None = None
    source: str | None = None
    # Search relevance metadata; present for name searches.
    match_rank: int | None = None


class DrugAlert(_OpenModel):
    """A regulatory notice, optionally associated with a registry product."""

    id: int | None = None
    reg_number: str | None = None
    product_name: str = "not supplied"
    alert_type: str | None = None
    alert_date: str | None = None
    reason: str | None = None
    source_link: str | None = None
    resolved_date: str | None = None
    active: bool = False
    matched_by: AlertMatchType
    product_id: int | None = None
    source_kind: Literal["regulatory", "synthetic", "unknown"] = "unknown"
    demo_label: str | None = None


class Mismatch(_OpenModel):
    """A difference between user-confirmed pack details and registry data."""

    field: str
    # Values may be strings or lists when multiple registry candidates exist.
    expected: Any = None
    observed: Any = None
    note: str


class Findings(_OpenModel):
    """Complete, structured result returned by the checking engine."""

    query: str
    query_type: QueryType | None = None
    status: Status
    reason: str | None = None
    matches: list[DrugMatch] = Field(default_factory=list)
    more_results: bool = False
    alerts: list[DrugAlert] = Field(default_factory=list)
    has_active_alert: bool = False
    mismatches: list[Mismatch] = Field(default_factory=list)
    data_as_of: str | None = None
    registry_data_status: dict[str, Any] = Field(default_factory=dict)
    alert_data_status: dict[str, Any] = Field(default_factory=dict)
    registry_scope: Literal["sample_demo", "unknown"] = "unknown"


def adapt_findings(payload: Any) -> Findings:
    """Validate a backend result and return the canonical Findings model.

    Accepts an existing Findings instance or a dictionary-like payload.
    Raises ContractError rather than allowing malformed data into the AI layer.
    """
    if isinstance(payload, Findings):
        return payload

    if not isinstance(payload, dict):
        raise ContractError("Backend findings must be a dictionary or Findings model")

    # Accept the legacy AI package spelling while keeping the shared model's
    # canonical query type aligned with the authoritative backend.
    if payload.get("query_type") == "registration_number":
        payload = {**payload, "query_type": "reg_number"}

    try:
        return Findings.model_validate(payload)
    except ValidationError as exc:
        raise ContractError(f"Backend findings failed contract validation: {exc}") from exc


class BackendLookup(Protocol):
    """Expected callable interface for a backend adapter."""

    def check_message(self, conn: Any, text: str) -> dict[str, Any]: ...

    def check_name(self, conn: Any, name: str, limit: int = 10) -> dict[str, Any]: ...

    def check_reg_number(self, conn: Any, reg_number: str) -> dict[str, Any]: ...

    def check_packet(self, conn: Any, details: dict[str, Any]) -> dict[str, Any]: ...


class ProposedBackendAdapter:
    """Thin adapter exposing engine functions through the shared interface.

    Import is delayed until construction so importing this contracts module
    does not create a circular dependency with the backend engine.
    """

    def __init__(
        self,
        lookup: Callable[[str, str], Any] | None = None,
    ) -> None:
        # A callback keeps legacy/demo callers testable without importing or
        # selecting the AI package's independent catalogue engine in production.
        self._lookup = lookup
        if lookup is not None:
            self._engine = None
            return
        try:
            from . import engine
        except ImportError as exc:
            raise ContractError(
                "Could not import the backend engine; use package-level imports"
            ) from exc

        self._engine = engine

    def check(self, query: str, query_type: str) -> Findings:
        """Use an explicitly injected test/demo lookup callback."""
        if self._lookup is None:
            raise ContractError("A lookup callback is required for this interface")
        return adapt_findings(self._lookup(query, query_type))

    def check_message(self, conn: Any, text: str) -> Findings:
        return adapt_findings(self._engine.check_message(conn, text))

    def check_name(self, conn: Any, name: str, limit: int = 10) -> Findings:
        return adapt_findings(self._engine.check_name(conn, name, limit=limit))

    def check_reg_number(self, conn: Any, reg_number: str) -> Findings:
        return adapt_findings(self._engine.check_reg_number(conn, reg_number))

    def check_packet(self, conn: Any, details: dict[str, Any]) -> Findings:
        return adapt_findings(self._engine.check_packet(conn, details))
