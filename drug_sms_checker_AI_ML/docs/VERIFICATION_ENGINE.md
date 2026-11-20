# Medicine Verification Engine — Stage 4

Date: 19 Nov 2026

## 1. Purpose and scope

This document describes the standalone, offline Medicine Identification and
Verification Engine implemented after
[`MEDICINE_DATABASE_READINESS_AUDIT.md`](MEDICINE_DATABASE_READINESS_AUDIT.md).

The engine is a **deterministic verification layer** for the standalone AI/ML
component. It separates:

1. candidate generation,
2. field-level comparison,
3. the final six-way verification decision.

It does **not** contact a backend, an external database, Gemini or any other
external AI API. It does not upload images, write source data, alter OCR source
records, or use OCR output as ground truth.

The local catalogue remains a **deterministic test catalogue**, not an
authoritative regulatory database. No regulatory authenticity claim is made by
this component.

---

## 2. Module layout

```text
src/catalogue.py       read-only catalogue loader, indexes, conservative parsers
src/observation.py     common SMS/OCR observation model and adapters
src/candidate.py       ranked candidate generation and retrieval evidence
src/field_compare.py   seven-field deterministic comparison
src/decision.py        six-way decision policy and human-readable reasons
src/verification.py    facade that composes the layers
```

Existing modules are reused without modification:

- `src/message.py` — SMS parsing and normalisation,
- `src/fuzzy.py` — calibrated `suggest()` / `WRatio` suggestion policy,
- `src/photo.py` — `PhotoFields`, `PhotoResult`, missing-value semantics,
- `src/packaging.py` — daylight/indoor reconciliation and ground-truth safety,
- `src/contracts.py` — unchanged proposed transport seam.

The engine result is deliberately **internal** and is not mapped into
`Findings` because `AWAITING_BACKEND_CONFIRMATION = True` remains unchanged.

---

## 3. Read-only and safety guarantees

The engine never modifies:

- `data/test_drugs.csv`
- `data/packaging/ocr_results.csv`
- `data/packaging/package_results.csv`
- `data/packaging/ground_truth.csv`
- original packaging images
- `.env`
- `src/contracts.py`
- existing tests
- the backend contract status

The catalogue loader reads all six existing columns and stores them verbatim in
`CatalogueProduct.original`. Blanks are missing (`None`); they are never filled
with guessed values. `applicant_name` is never copied into `manufacturer`.

OCR values are observations only. `accuracy_tested` is always `False` unless
independent ground truth exists, and the current ground truth file is empty.
Real-pack OCR accuracy remains **NOT TESTED**.

---

## 4. Catalogue rules

`MedicineCatalogue` builds exact in-memory indexes:

| Index | Rule |
| --- | --- |
| Registration number | Exact after case and hyphen-glyph normalisation only; never fuzzy |
| Brand name | Case, punctuation-boundary and whitespace normalisation |
| Generic name | Case/punctuation normalisation, Greek α/β transliteration, semicolon ingredients treated as a set |

Important behaviour:

- registration-number lookup is prioritised;
- an exact generic name returns **all** matching products;
- no first-row collapse is performed;
- duplicate registration numbers and blank required values are rejected;
- strength and package volume are parsed separately from existing brand text;
- package volume such as `100 ml` is never parsed as strength;
- a dosage form is derived only when an explicit token appears in source text.

Example: `Paracetamol` returns both `AC-Mol Drops` and `Acepol Suspension`.
The four `α-β Arteether` products are also preserved as four distinct products.

---

## 5. Observation model

`MedicineObservation` carries seven logical fields:

```text
registration_number
brand_name
generic_name
manufacturer
strength
dosage_form
package_volume
```

Each field is an `ObservedField` with:

- `value` — usable value or `None`,
- `raw` — original text,
- `status` — `PRESENT`, `MISSING`, `NOT_VISIBLE` or `CONFLICT`,
- `provenance` — source field, message span, capture or CSV column.

The model also carries source reconciliation statuses, manual-review flags and
an `accuracy_tested` flag. Package volume is always separate from strength.

### Adapters

| Adapter | Reuses | Notes |
| --- | --- | --- |
| `from_message_intent()` | `src.message.parse_message` | Preserves original message and extraction metadata |
| `from_photo_fields()` / `from_photo_result()` | `src.photo` | Four extracted fields only; never ground truth |
| `from_image_level_ocr_row()` | `ocr_results.csv` | One daylight/indoor capture |
| `from_package_result()` | `package_results.csv` | Preserves all reconciliation statuses and conflicts |

A genuine OCR `CONFLICT` is not converted into a value. The competing original
values are retained in `raw`, and the conflict marker itself is never compared
as text.

---

## 6. Candidate generation

Retrieval paths are ranked:

1. `registration_number_exact`
2. `brand_name_exact`
3. `generic_name_exact`
4. `fuzzy_brand_name`
5. `fuzzy_generic_name`

Rules:

- exact registration-number evidence is always first;
- a present but unmatched registration number suppresses fuzzy name guessing;
- an exact brand still retrieves a candidate when the registration number is
  wrong, so a direct `MISMATCH` can be reported;
- exact generic matches preserve every product;
- a single SMS name field is also checked against generic names;
- duplicate retrieval paths for one product are merged into one candidate;
- candidates from fuzzy paths always require confirmation.

### Similarity policy

Fuzzy retrieval calls the existing `suggest()` policy (`CUTOFF = 72`,
`AMBIGUOUS_GAP = 6`, `SHORT_NAME_LENGTH = 5`). Scores are exposed only as
`similarity_score`. They are string-similarity measures, **not probabilities,
percentages or verification confidence**, and they never prove identity.

---

## 7. Field comparison

`compare_fields()` always returns these seven rows in a stable order:

```text
registration_number, brand_name, generic_name, manufacturer,
strength, dosage_form, package_volume
```

Field statuses:

| Status | Meaning |
| --- | --- |
| `MATCH` | Both sides are present and compare equal under the documented rule |
| `MISMATCH` | Both sides are present and directly conflict |
| `UNKNOWN` | A side is missing, not visible or unavailable in the catalogue |
| `UNPARSED` | A value is present but cannot be safely parsed with an explicit unit/token |
| `CONFLICT` | The observation itself contains conflicting values |

Comparison rules:

- registration numbers: exact only after safe normalisation;
- brand names: conservative normalisation; fuzzy score is supporting only;
- generic names: exact ingredient-set match; repeated generics remain ambiguous;
- manufacturer: compared only when both sides are populated;
- strength: numeric value plus explicit unit, with safe mcg conversion;
- dosage form: explicit token match, supportive only;
- package volume: compared in millilitres, separate from strength.

Every comparison preserves `observed_raw`, `catalogue_raw`, normalised values,
a reason and provenance.

---

## 8. Six-way decision policy

The internal status vocabulary is exactly:

```text
MATCH
PARTIAL_MATCH
MISMATCH
NO_MATCH
INSUFFICIENT_INFORMATION
MANUAL_REVIEW_REQUIRED
```

| Status | Applied when |
| --- | --- |
| `MATCH` | One unique candidate, exact registration evidence or exact brand plus independent support, and no conflicts |
| `PARTIAL_MATCH` | One plausible candidate but support is missing/weak; also exact NRN with only a similar brand |
| `MISMATCH` | A candidate is identified but an observed field directly conflicts |
| `NO_MATCH` | Searchable evidence exists, but no catalogue candidate was found |
| `INSUFFICIENT_INFORMATION` | No usable registration number, brand name or generic name was supplied |
| `MANUAL_REVIEW_REQUIRED` | OCR/source conflict, multiple candidates, fuzzy/generic-only confirmation, or unparsed observed value |

Important distinctions:

- `NO_MATCH` means “enough to search, nothing found”.
- `INSUFFICIENT_INFORMATION` means “not enough to decide”.
- `MISMATCH` means “identified, but a field conflicts”.
- `PARTIAL_MATCH` means “likely identity, incomplete verification”.

Every result includes human-readable `reasons` and `status_explanation`. No
numeric confidence field or percentage is emitted.

---

## 9. Packaging sample behaviour

The current 11 packs do not overlap the 40-row catalogue: registration numbers
`04-1436`, `04-1860` and `04-3230` are absent, and no packaging brand name is
an exact catalogue brand.

Therefore the correct current result is:

- `NO_MATCH` for sufficient-but-absent observations, or
- `MANUAL_REVIEW_REQUIRED` where fuzzy/generic ambiguity or a genuine OCR
  conflict exists.

The engine must not force a `MATCH` for these samples. `pack_10` retains its
genuine brand conflict and yields `MANUAL_REVIEW_REQUIRED`.

---

## 10. Test coverage

New offline test files:

```text
tests/test_catalogue.py
tests/test_candidate.py
tests/test_field_compare.py
tests/test_decision.py
tests/test_verification.py
```

They cover:

- all six source columns and original-value preservation,
- blank-as-missing and applicant-not-manufacturer rules,
- exact registration/brand/generic indexes and generic collisions,
- invalid/duplicate/missing-column catalogue rejection,
- strength versus volume parsing,
- registration-number priority and fuzzy suppression,
- all seven field comparisons,
- all six decision statuses,
- OCR conflicts, provenance and ground-truth safety,
- SMS and packaging adapters,
- no confidence/probability fields in internal results,
- byte-for-byte preservation of protected CSVs during engine tests.

Existing tests were not modified, skipped or weakened.

Full offline result at implementation time:

```text
182 passed, 40 skipped, 2 warnings in 4.52s
```

The 40 skipped tests are live Gemini tests requiring `--run-live`. The two
warnings are third-party deprecation warnings from `anyio` and `google-genai`,
not project test failures.

---

## 11. Exact local demonstration commands

Open PowerShell in the project directory:

```powershell
cd "C:\Users\DELL\Documents\Default Project"
```

### Full offline suite

```powershell
python -m pytest -q
```

### New verification-engine tests only

```powershell
python -m pytest -q tests/test_catalogue.py tests/test_candidate.py tests/test_field_compare.py tests/test_decision.py tests/test_verification.py
```

### Demonstrate all six statuses

```powershell
@'
from src.observation import MedicineObservation, ObservedField
from src.verification import VerificationEngine

engine = VerificationEngine()

cases = {
    "MATCH": engine.verify_sms("check B4-1180"),
    "PARTIAL_MATCH": engine.verify_sms("check Acimox Capsule"),
    "MISMATCH": engine.verify(
        MedicineObservation(
            observation_id="DEMO-MISMATCH",
            source_channel="sms",
            registration_number=ObservedField.present("ZZ-9999"),
            brand_name=ObservedField.present("Acimox Capsule"),
        )
    ),
    "NO_MATCH": engine.verify_sms("check ZZ-9999"),
    "INSUFFICIENT_INFORMATION": engine.verify_sms("hello"),
    "MANUAL_REVIEW_REQUIRED": engine.verify_sms("check Ablept 300 Capusles"),
}

for expected, result in cases.items():
    assert result.status == expected, (expected, result.status)
    print(f"{expected}: {result.status}")
    print("  " + result.reasons[0])
'@ | python -
```

### Demonstrate packaging OCR isolation

```powershell
@'
from src.verification import VerificationEngine

engine = VerificationEngine()
results = engine.verify_package_results()

print("packs:", len(results))
for result in results:
    print(result.observation_id, result.status)
    print(" ", result.reasons[0])

assert len(results) == 11
assert not any(result.status == "MATCH" for result in results)
assert next(r for r in results if r.observation_id == "PACK-pack_10").status == "MANUAL_REVIEW_REQUIRED"
'@ | python -
```

### Demonstrate generic-name collision preservation

```powershell
@'
from src.verification import VerificationEngine

engine = VerificationEngine()
result = engine.verify_sms("check Paracetamol")

print(result.status)
for candidate in result.candidates.candidates:
    print(candidate.product.brand_name, candidate.product.registration_number)

assert result.status == "MANUAL_REVIEW_REQUIRED"
assert len(result.candidates.candidates) == 2
'@ | python -
```

---

## 12. Known limitations

1. The catalogue has only 40 records and is not authoritative.
2. Manufacturer is populated in only 5 of 40 rows, so most manufacturer checks
   remain `UNKNOWN`.
3. Strength and dosage form are embedded in free-text brand names, so derived
   parsing is conservative and can be `UNPARSED` or `UNKNOWN`.
4. No registry status, alert data, aliases or product identifiers exist beyond
   the six source columns.
5. Fuzzy scores are calibrated for spelling suggestions, not clinical or
   regulatory verification.
6. Real-pack OCR accuracy is untested because independent ground truth is empty.
7. Mapping into backend `Findings` remains deferred until
   `AWAITING_BACKEND_CONFIRMATION` becomes `False`.

---

## 13. Bottom line

The Stage 4 engine is a deterministic, explainable, offline candidate-and-field
verification layer. It preserves source data, separates evidence types, keeps
fuzzy similarity as a suggestion, treats OCR as untrusted observation data, and
produces one of exactly six internal statuses with human-readable reasons. It
does not claim regulatory authenticity and does not change the shared backend
contract.
