"""Small end-to-end check through the proposed backend seam."""

import pytest

from conftest import CATALOGUE_CSV
from src.contracts import ProposedBackendAdapter, adapt_findings
from src.fuzzy import DrugCatalogue
from src.gemini import GeminiClient
from src.pipeline import explain, prepare_lookup

CATALOGUE = DrugCatalogue.from_csv(CATALOGUE_CSV)
FINDINGS = {
    "query": "ZZ-1234",
    "query_type": "registration_number",
    "status": "found",
    "matches": [{
        "reg_number": "ZZ-1234",
        "brand_name": "SyntheticTestBrand",
        "registry_status": "Registered",
        "source": "SYNTHETIC TEST RECORD",
    }],
    "alerts": [],
    "mismatches": [],
    "data_as_of": "19 Nov 2026 (synthetic)",
}


def fake_lookup(query: str, query_type: str) -> dict:
    assert query == "ZZ-1234"
    assert query_type == "registration_number"
    return FINDINGS


def test_message_to_findings_to_explanation():
    prepared = prepare_lookup("abeg check ZZ-1234", CATALOGUE)
    assert prepared.stage == "ready"
    assert prepared.await_confirmation is False
    assert prepared.lookup_query == "ZZ-1234"

    adapter = ProposedBackendAdapter(fake_lookup)
    findings = adapter.check(prepared.lookup_query, prepared.lookup_type)
    out = explain("check ZZ-1234", findings, GeminiClient(force_mock=True))
    assert "Data as of: 19 Nov 2026 (synthetic)." in out.reply
    assert "SyntheticTestBrand" in out.reply
    assert "safe" not in out.reply.lower()


def test_fuzzy_correction_requires_confirmation_before_lookup():
    prepared = prepare_lookup("check Ablept 300 Capusles", CATALOGUE)
    assert prepared.stage == "await_confirmation"
    assert prepared.await_confirmation is True
    assert prepared.lookup_query is None


def test_contract_never_invents_missing_fields():
    parsed = adapt_findings({"status": "not_found", "query": "X"})
    assert parsed.matches == []
    assert parsed.alerts == []
    assert parsed.data_as_of is None
    assert "data_as_of was not supplied" in explain("check X", parsed).reply


def test_invalid_contract_is_rejected():
    with pytest.raises(ValueError):
        adapt_findings({"status": "maybe", "matches": "none"})
