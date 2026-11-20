"""30 misspellings: correct candidate or explicit clarification, never silent substitution."""

import pytest

from conftest import CATALOGUE_CSV
from src.fuzzy import DrugCatalogue, suggest

CATALOGUE = DrugCatalogue.from_csv(CATALOGUE_CSV)

# (misspelled query, expected top brand). None means ambiguity/clarification is acceptable.
CASES = [
    ("Ablept 300 Capusles", "Ablept 300 Capsules"),
    ("Ablept 300 Capules", "Ablept 300 Capsules"),
    ("Acimox Capsul", "Acimox Capsule"),
    ("Actifed Cold Tabletz", "Actifed Cold Tablets"),
    ("Actifed COLD TABLETS", "Actifed Cold Tablets"),
    ("Acupan Injecction", "Acupan Injection"),
    ("Acdazin Creme", "Acdazin Cream"),
    ("Acepol Suspention", "Acepol Suspension"),
    ("Abther 150 Inj", "Abther 150 Injection"),
    ("Abther 225 Injection", "Abther 225 Injection"),
    ("Abeemal Injecton", "Abeemal Injection"),
    ("Abdoe Bismuth", "Abdoe-Bismuth"),
    ("3-Xon Creme", "3-Xon Cream"),
    ("AC-Ome 20 Capsul", "AC-Ome 20 Capsule"),
    ("AC-Mol Drop", "AC-Mol Drops"),
    ("AC-Ibu 200 Tabletz", "AC-Ibu 200 Tablet"),
    ("AC-Diclo 100 Tablett", "AC-Diclo 100 Tablet"),
    ("AC-Drex Tablete", "AC-Drex Tablet"),
    ("AC-Fed Tablets", "AC-Fed Tablet"),
    ("AC-Motil Capsul", "AC-Motil Capsule"),
    ("AC-Tramadol Capsules", "AC-Tramadol Capsule"),
    ("Accesslife Pentazocine Injec", "Accesslife Pentazocine Injection"),
    ("Accesslife Tramadol Capsul", "Accesslife Tramadol Capsules"),
    ("Aciclovir Creme BP 5%", "Aciclovir Cream BP 5% w/w"),
    ("Actinac 100 Tablets", "Actinac 100 Tablets"),
    ("1980 Pregablin 150 mg Capsules", "1980 Pregabalin 150 mg Capsules"),
    ("1980 Azithromycin USP 250 mg Tabletz", "1980 Azithromycin USP 250 mg Tablets"),
    ("A-B Arteether Inj", "A-B Arteether Injection"),
    ("Acimox Cap", "Acimox Capsule"),
    ("AC MOL DROPS", "AC-Mol Drops"),  # hyphen/punctuation variant
    ("Acimox Capsulee", "Acimox Capsule"),
    ("ema-500 Tablets", None),  # truncated: clarification is the safe outcome
]


@pytest.mark.parametrize("query,expected", CASES)
def test_misspelling_candidates(query, expected):
    result = suggest(query, CATALOGUE)
    assert result.status in {"exact", "suggest", "ambiguous", "clarify"}
    if result.status in {"suggest", "ambiguous", "exact"}:
        assert result.candidates
    if expected and result.status != "clarify":
        top = result.candidates[0].brand_name
        assert top == expected, f"{query!r}: got {result.status} -> {top}, expected {expected}"
    if expected is None:
        assert result.status in {"clarify", "ambiguous"}
    # A fuzzy correction may never be applied without the user's confirmation.
    if result.status != "exact":
        assert result.requires_confirmation is True
    if result.status == "exact":
        assert result.candidates[0].score == 100.0


def test_zero_silent_wrong_selection():
    """No result may mark a fuzzy candidate as ready for lookup."""
    wrong = suggest("Acimox Suspension", CATALOGUE)
    assert wrong.requires_confirmation or wrong.status == "clarify"


def test_short_name_asks_for_choice():
    result = suggest("ab", CATALOGUE)
    assert result.status in {"ambiguous", "clarify"}
