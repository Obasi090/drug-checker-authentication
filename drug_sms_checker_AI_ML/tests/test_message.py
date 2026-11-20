"""40 messy messages: case, spaces, hyphen variants, Pidgin, typos and fillers."""

import pytest

from conftest import CATALOGUE_CSV
from src.fuzzy import DrugCatalogue
from src.message import normalize, parse_message

CATALOGUE = DrugCatalogue.from_csv(CATALOGUE_CSV)
NAMES = [e.brand_name for e in CATALOGUE.entries]

# (message, expected registration number, expected name, expected intent)
CASES = [
    ("pls check ZZ-1234", "ZZ-1234", None, "lookup"),
    ("ABEG wetin be Ablept 300 Capsules", None, "Ablept 300 Capsules", "lookup"),
    ("check ablept 300 capules", None, "ablept 300 capules", "lookup"),
    ("ZZ-1234 na true?", "ZZ-1234", None, "lookup"),
    ("I want to check the status of A4-101970", "A4-101970", None, "lookup"),
    ("hello, please verify B4-1180 for me", "B4-1180", None, "lookup"),
    ("how much should i take of Ablept?", None, None, "medical_question"),
    ("side effects of Acimox", None, None, "medical_question"),
    ("can I take Acimox with alcohol?", None, None, "medical_question"),
    ("pregabalin dose please", None, None, "medical_question"),
    ("my head hurts what medicine", None, None, "clarify"),
    ("what drug treats malaria", None, None, "medical_question"),
    ("check", None, None, "clarify"),
    ("", None, None, "clarify"),
    ("   ", None, None, "clarify"),
    ("A4 101970", None, None, "clarify"),
    ("A4–101970", "A4–101970", None, "lookup"),
    ("A4 - 101970", None, None, "clarify"),
    ("abeg check abther 150 injection", None, "Abther 150 Injection", "lookup"),
    ("please check AC-Ome 20 Capsule", None, "AC-Ome 20 Capsule", "lookup"),
    ("Plz verify 04-1984", "04-1984", None, "lookup"),
    ("search for Actifed Cold Tablets", None, "Actifed Cold Tablets", "lookup"),
    ("find 3-Xon Cream", None, "3-Xon Cream", "lookup"),
    ("verify Abdoe-Bismuth", None, "Abdoe-Bismuth", "lookup"),
    ("check Aciclovir Cream BP 5% w/w", None, "Aciclovir Cream BP 5% w/w", "lookup"),
    ("check Acimox suspension", None, "acimox suspension", "lookup"),
    ("wetin be 1980 Ceftriaxone 1 g Injection", None, "1980 ceftriaxone 1 g injection", "lookup"),
    ("how far with Ablept 300 Capsules", None, "Ablept 300 Capsules", "lookup"),
    ("check am", None, None, "clarify"),
    ("NAFDAC reg no A11-0550", "A11-0550", None, "lookup"),
    ("A4-101970 is it genuine?", "A4-101970", None, "lookup"),
    ("check ZZ-1234 and provide dosage", "ZZ-1234", None, "medical_question"),
    ("check A4-101970 please abeg", "A4-101970", None, "lookup"),
    ("  CHECK   AC-Drex   TABLET  ", None, "AC-Drex Tablet", "lookup"),
    ("abeg, check Accesslife Tramadol Capsules", None, "Accesslife Tramadol Capsules", "lookup"),
    ("I dey find Acem-500 Tablets", None, "Acem-500 Tablets", "lookup"),
    ("wetindey for Abther 225 Injection", None, "Abther 225 Injection", "lookup"),
    ("check A11 0236", None, None, "clarify"),
    ("check 04-0858", "04-0858", None, "lookup"),
    ("pls abeg check B4-9460", "B4-9460", None, "lookup"),
    ("abeg check", None, None, "clarify"),
    ("what is the registration number?", None, None, "clarify"),
    ("my friend told me about this drug", None, None, "clarify"),
    ("check ZZ-1234ab", None, None, "clarify"),
    ("check A4–101970 and AC-Mol Drops", "A4–101970", "AC-Mol Drops", "lookup"),
]


@pytest.mark.parametrize("message,reg,name,intent", CASES)
def test_messy_message_extraction(message, reg, name, intent):
    parsed = parse_message(message, NAMES)
    assert parsed.registration_number == reg
    assert parsed.name == name
    assert parsed.intent == intent
    assert parsed.medical_question == (intent == "medical_question")
    assert parsed.needs_clarification == (intent == "clarify")
    # Filler removal must not mutate traceability.
    assert parsed.original == message
    assert parsed.normalized == normalize(message)
