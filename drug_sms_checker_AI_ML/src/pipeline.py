"""Small orchestration helpers for the web/backend integration seam."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .contracts import Findings, adapt_findings
from .fuzzy import DrugCatalogue, Suggestion, suggest
from .gemini import Explanation, GeminiClient, mock_explain
from .message import MessageIntent, parse_message


class PreparedLookup(BaseModel):
    intent: MessageIntent
    suggestion: Suggestion | None = None
    stage: str
    await_confirmation: bool
    lookup_query: str | None = None
    lookup_type: str | None = None


def prepare_lookup(text: str, catalogue: DrugCatalogue, client: GeminiClient | None = None) -> PreparedLookup:
    """Determine what can be sent to the engine, without sending it."""
    intent = parse_message(text, [e.brand_name for e in catalogue.entries])
    if intent.needs_clarification and client is not None and client.available:
        extracted = client.extract_intent(text)
        if extracted.registration_number or extracted.name:
            intent.registration_number = extracted.registration_number
            intent.name = extracted.name
            intent.extracted_by = "gemini"
            intent.needs_clarification = False
            intent.intent = "lookup"

    if intent.registration_number:
        return PreparedLookup(intent=intent, stage="ready", await_confirmation=False,
                              lookup_query=intent.registration_number, lookup_type="registration_number")

    if intent.name:
        result = suggest(intent.name, catalogue)
        if result.status == "exact":
            candidate = result.candidates[0]
            return PreparedLookup(intent=intent, suggestion=result, stage="ready",
                                  await_confirmation=False,
                                  lookup_query=candidate.registration_number or candidate.value,
                                  lookup_type="registration_number" if candidate.registration_number else "name")
        return PreparedLookup(intent=intent, suggestion=result, stage="await_confirmation",
                              await_confirmation=True)

    return PreparedLookup(intent=intent, stage="clarify", await_confirmation=False)


def explain(question: str, payload: dict[str, Any] | Findings, client: GeminiClient | None = None) -> Explanation:
    findings = payload if isinstance(payload, Findings) else adapt_findings(payload)
    if client is None:
        return mock_explain(question, findings)
    return client.explain(question, findings)
