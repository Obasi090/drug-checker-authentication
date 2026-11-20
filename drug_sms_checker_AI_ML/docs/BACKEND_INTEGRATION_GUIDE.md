# BACKEND INTEGRATION GUIDE — Drug SMS Checker AI/ML

Date: 19 Nov 2026
Audience: backend development team
Status: **PROPOSED — REQUIRES BACKEND APPROVAL** for all integration interfaces described here.

This guide documents the *actual* public functions, models and return structures in this frozen release copy. It does **not** invent HTTP endpoints, routes or an approved API contract. There is no backend wiring in this component today. `src/contracts.py` is explicitly marked `PROPOSED` and `AWAITING_BACKEND_CONFIRMATION = True`; do not change that flag until the backend owner approves.

> **Three rules that must survive integration:**
> 1. Keep `UNKNOWN`, `MISMATCH` and `CONFLICT` as **distinct** states. `UNKNOWN` means information was not supplied; it is not a mismatch.
> 2. `similarity_score` is a retrieval hint only — **never** confidence, probability, a percentage or identity evidence.
> 3. OCR/Gemini values are **observations**, not proof of medicine authenticity and not verified ground truth.

---

## 1. Expected input information

The engine consumes a channel-neutral `MedicineObservation` with seven observed fields:

`registration_number`, `brand_name`, `generic_name`, `manufacturer`, `strength`, `dosage_form`, `package_volume`.

Each field is an `ObservedField`:

```python
class ObservedField(BaseModel):            # extra="forbid"
    value: str | None = None               # usable value, or None
    raw: str | None = None                 # original text, preserved
    status: Literal["PRESENT", "MISSING", "NOT_VISIBLE", "CONFLICT"] = "MISSING"
    provenance: str = ""                   # source label chosen by the caller
```

Factories: `ObservedField.present(value, provenance="")`, `.missing(provenance="")`, `.not_visible(raw, provenance="")`, `.conflict(daylight, indoor, provenance="")`. `usable` is true only for `PRESENT` with a non-empty value.

`MedicineObservation` fields: `observation_id`, `source_channel` (`"sms" | "daylight_ocr" | "indoor_ocr" | "consolidated_ocr"`), the seven fields above, `source_field_statuses`, `source_manual_review_required`, `source_manual_review_fields`, `provenance`, `accuracy_tested`, `notes`.

## 2. SMS processing entry point

**Recommended, simplest:**

```python
from src.verification import VerificationEngine

engine = VerificationEngine()
result = engine.verify_sms("check B4-1180", observation_id="SMS-1")
print(result.status, result.selected_product_id)
for reason in result.reasons:
    print("-", reason)
```

Signature: `VerificationEngine.verify_sms(text, *, known_names=None, observation_id="SMS-1") -> VerificationResult`.

Convenience one-off: `verify_sms_text(text, *, catalogue=None, observation_id="SMS-1") -> VerificationResult`.

Lower-level parsing: `src.message.parse_message(text, known_names=None) -> MessageIntent` with fields `original`, `normalized`, `registration_number`, `name`, `intent`, `medical_question`, `needs_clarification`, `extracted_by`, `notes`. The adapter `observation_from_sms_text(text, brand_names, observation_id)` builds the observation while preserving the original message and parser provenance.

`src.pipeline.prepare_lookup(text, catalogue, client=None) -> PreparedLookup` is a **PROPOSED** confirmation-gating helper for a future backend; it does not send anything to the engine.

## 3. Image extraction entry point

```python
from pathlib import Path
from src.gemini import GeminiClient
from src.photo import extract_photo_fields
from src.verification import VerificationEngine

client = GeminiClient()                       # loads configured key via existing loader
photo = extract_photo_fields(
    Path("data/packaging/daylight/pack_01.jpeg").read_bytes(),
    "image/jpeg",
    client,
)
print(photo.status, photo.message)            # ok | rejected | NOT TESTED | error
if photo.status == "ok":
    result = VerificationEngine().verify_photo_result(photo, observation_id="PHOTO-1")
```

Signatures:
- `extract_photo_fields(image_bytes: bytes, mime_type: str, client=None) -> PhotoResult`
- `GeminiClient.read_photo(image_bytes: bytes, mime_type: str) -> dict` (validated into `PhotoFields`)
- `VerificationEngine.verify_photo_result(result: PhotoResult, *, observation_id="PHOTO-1") -> VerificationResult`

`PhotoFields` (`extra="forbid"`) has exactly four fields: `brand_name`, `registration_number`, `manufacturer`, `strength`, each defaulting to the literal `"not visible"`. `PhotoResult` has `fields`, `status`, `accuracy_tested=False`, `message`. **Package volume is not extracted** and must not be derived from strength.

## 4. Observation structure (backend-supplied)

```python
from src.observation import MedicineObservation, ObservedField

observation = MedicineObservation(
    observation_id="API-42",
    source_channel="sms",
    registration_number=ObservedField.present("B4-1180", "backend-sms"),
    generic_name=ObservedField.present("Gabapentin", "backend-sms"),
    strength=ObservedField.missing("backend-sms"),
)
result = engine.verify(observation)
```

Never fill an unknown fact with a guess. Use `.missing()` or `.not_visible()`; if two original values disagree, use `.conflict(a, b)` so both raw strings survive.

## 5. Candidate generation

`engine.verify(observation)` calls `generate_candidates(observation, catalogue, fuzzy_catalogue=..., limit=5) -> CandidateSet`. You may also call it directly with `src.candidate.generate_candidates`.

`CandidateSet`: `candidates: list[CandidateEvidence]`, `exact_registration_product_id`, `fuzzy_suggestions_used`, `ambiguous`, `requires_confirmation`, `reasons`, `search_summary`.

`CandidateEvidence`: `product: CatalogueProduct`, `matched_by: MatchMethod`, `matched_paths`, `matched_values`, `similarity_score: float | None`, `requires_confirmation: bool`, `reasons`. `identity_label` is a property.

`MatchMethod` values: `registration_number_exact`, `brand_name_exact`, `generic_name_exact`, `fuzzy_brand_name`, `fuzzy_generic_name`. Exact registration has priority; an unknown registration is never converted into a fuzzy name guess; exact generic returns all matching products.

Catalogue helpers: `load_catalogue(path=None)`, `MedicineCatalogue.registration_lookup(value)`, `.brand_lookup(value)`, `.generic_lookup(value)`, `.brand_names`.

## 6. Field comparison

`src.field_compare.compare_fields(observation, product) -> tuple[FieldComparison, ...]` compares seven fields in stable order.

`FieldComparison`: `field`, `status`, `observed_raw`, `catalogue_raw`, `observed_normalized`, `catalogue_normalized`, `reason`, `similarity_score`, `provenance`.

`FieldStatus` = `MATCH | MISMATCH | UNKNOWN | UNPARSED | CONFLICT`. Registration is exact-only. `FieldComparison.is_negative_evidence` is available for review filtering. In the facade result, comparisons are grouped by `product_id` in `VerificationResult.field_comparisons`.

## 7. Verification result structure

`VerificationResult` (`extra="forbid"`) fields:

| Field | Meaning |
| --- | --- |
| `observation_id`, `source_channel` | Caller identifiers |
| `status` | One of the six decisions |
| `reasons`, `status_explanation` | Human-readable evidence and explanation |
| `selected_product_id`, `selected_candidate` | Present only when a product was actually selected |
| `candidates` | Full `CandidateSet`, including unselected products |
| `field_comparisons` | `dict[product_id, list[FieldComparison]]` |
| `review_fields`, `missing_fields` | Distinct review and absence lists |
| `provenance` | Original observation provenance |
| `accuracy_tested` | Always `False` in this engine |
| `catalogue_sha256` | Hash of the loaded test catalogue |
| `notes` | Safety caveats |
| `is_manual_review` (property) | True only for `MANUAL_REVIEW_REQUIRED` |

This result is **internal**; it is intentionally separate from the PROPOSED backend `Findings` model.

## 8. Six decision statuses

`VerificationStatus = MATCH | PARTIAL_MATCH | MISMATCH | NO_MATCH | INSUFFICIENT_INFORMATION | MANUAL_REVIEW_REQUIRED`.

| Status | Meaning for the backend |
| --- | --- |
| `MATCH` | Exact registration, corroborating fields, no conflicts. Still not an authenticity claim. |
| `PARTIAL_MATCH` | One exact brand hit without independent corroboration; do not auto-accept. |
| `MISMATCH` | A comparable field contradicts the selected product. |
| `NO_MATCH` | Searchable registration supplied but absent from the test catalogue; catalogue may be incomplete. |
| `INSUFFICIENT_INFORMATION` | No usable registration, brand or generic name. |
| `MANUAL_REVIEW_REQUIRED` | Conflict, ambiguity or unconfirmed suggestion; requires a human. |

## 9. Error handling

`PhotoResult.status` values: `ok`, `rejected` (upload validation), `NOT TESTED` (no usable key), `error` (API/classification/malformed response). `PhotoReadError` carries only a safe `kind`, optional `code`/`status`; raw bodies, request metadata and credentials are never surfaced. `GeminiClient.explain()` returns an `Explanation` with `used_mock`/`used_fallback` flags and degrades safely. Catalogue validation raises `CatalogueError` / `ValueError`. No failure fabricates a value or a verification decision.

## 10. Missing information

Missing means "not supplied", represented as `MISSING` (observation) or `UNKNOWN` (comparison). It must be rendered as "not supplied / unknown" in any backend UI. `VerificationResult.missing_fields` lists those fields. Never collapse `UNKNOWN` into `MISMATCH`, never render it as a failed check, and never infer a value from another field.

## 11. Conflicting information

`ObservedField.conflict(daylight, indoor)` keeps both raw values with a `||` separator and `status="CONFLICT"`. `FieldComparison` also has a `CONFLICT` status. `VerificationResult.review_fields` names fields needing human attention. Conflicts must not be averaged, overwritten or silently resolved by the backend.

## 12. Manual-review requirements

When `status == "MANUAL_REVIEW_REQUIRED"` (or `is_manual_review` is true), the backend must stop any automatic acceptance path and present candidates, raw values, reasons and `review_fields` to a human. This applies to `pack_01`, `pack_04` and `pack_10` in the packaged dataset; `pack_10` must retain its brand conflict. Never force a packaging record to `MATCH`.

## 13. Asynchronous Gemini operations and latency

Gemini calls are network-bound: the SDK is configured with a 15,000 ms timeout and at most two attempts. Observed local extraction times were 7.6 s (single direct request), 5.0 s (UI image path) and 4.2 s for a two-image pair. One earlier expanded batch stopped at the 180-second limit. Backend callers should therefore enqueue image/explanation work asynchronously, set their own end-to-end deadline, show a loading state, and never block an SMS verification on a Gemini request. Offline SMS verification needs no network at all.

## 14. API key configuration and secret handling — PROPOSED

The release contains `.env.example` with **placeholder values only** for the three variables actually read by `src/gemini.py`:

- `GEMINI_API_KEY` — required for live Gemini operations;
- `GEMINI_MODEL` — optional override, default `gemini-3.1-flash-lite`;
- `AI_ML_MOCK` — `1` forces deterministic mocked responses; `0` permits live calls.

`GeminiClient.__init__()` calls the existing `load_project_env()`, which uses `python-dotenv` with `override=False`: **host environment variables and secrets-manager values win over `.env`.** The backend team must supply `GEMINI_API_KEY` through its secure environment-variable or secrets-management mechanism; the application then loads it through this existing implementation. No new configuration variable is required.

Offline functionality works with **no key** (or `AI_ML_MOCK=1`): verification, packaging reconciliation, the offline demo and all 182 offline tests run normally; photo extraction returns `NOT TESTED`. Live functionality works when a **valid key** is configured and `AI_ML_MOCK=0`: `GeminiClient().available` becomes `True` and bounded explanation, intent and four-field image extraction calls are available. Availability is a boolean property; the key value is never printed, logged or returned.

The real key from the original working project was deliberately **not packaged**. It must be transferred separately through a secure channel. Do not put a key in the ZIP, documentation, source code, logs, the release manifest, `.env.example`, or an ordinary email/chat message. No live validation was performed during packaging and no key was exposed.

## 15. Suggested integration flow — PROPOSED — REQUIRES BACKEND APPROVAL

```text
Backend receives SMS or image
  -> build MedicineObservation (never invent values)
  -> VerificationEngine.verify(observation)
  -> if status != MANUAL_REVIEW_REQUIRED and confirmation requirements satisfied:
        show result with all candidates/comparisons/reasons
     else:
        route to human review with raw values intact
  -> optionally, asynchronously: GeminiClient.explain(question, PROPOSED Findings)
  -> render explanation with used_mock/used_fallback visible
```

PROPOSED `Findings` (from `src/contracts.py`, `extra="allow"`): `query`, `query_type`, `status` (`found | multiple | not_found | invalid`), `matches: list[DrugMatch]`, `alerts: list[DrugAlert]`, `mismatches: list[Mismatch]`, `data_as_of`. `adapt_findings(payload)` validates a backend payload without fabricating facts. `Mismatch` is explicitly provisional — the backend must confirm its real fields. `ProposedBackendAdapter` is a protocol example only.

**Do not** treat `Findings`, `ProposedBackendAdapter`, `pipeline.prepare_lookup`, or any example above as an approved API contract. Do not change `AWAITING_BACKEND_CONFIRMATION` until the backend owner signs off.

## Verification example (all real APIs)

```python
from src.verification import VerificationEngine, verify_sms_text
from src.packaging import read_csv_rows, reconcile_packaging
from src.photo import is_missing

engine = VerificationEngine()
sms = engine.verify_sms("check Paracetamol")     # MANUAL_REVIEW_REQUIRED, 2 candidates
batch = engine.verify_package_results()          # 11 rows, no forced MATCH
assert all(item.accuracy_tested is False for item in batch)
```
