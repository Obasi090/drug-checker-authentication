# AI/ML Comprehensive Functionality Audit - Stage 5.3

Date: 19 Nov 2026
Component status: **FROZEN** - no core implementation was modified for this audit.
Method: direct source inspection, deterministic probes against the real engine and
catalogue, preserved packaging records, the existing offline suite, and a small
number of controlled live Gemini operations. No feature was marked working solely
because its source file exists.

## 1. Direct answers to the audit questions

| Question | Answer |
| --- | --- |
| Is the AI/ML system genuinely implemented? | **Yes.** Every inspected module contains working logic and was exercised; none is a stub. |
| Which features have been tested successfully? | Catalogue loading, SMS parsing, observation states, retrieval, fuzzy suggestion, seven-field comparison, six-status decisions, packaging reconciliation, ground-truth safety, Gemini explanation/intent/image paths, and error handling. |
| Which features have only been tested offline? | The deterministic engine, all 11 packaging records, all safety guards, and all 182 offline tests. Mocked Gemini tests validate logic, not the live service. |
| Which features have been tested with real Gemini requests? | Explanation, intent extraction (earlier controlled suite), and image extraction. Live validation remains **PARTIAL**, not full. |
| Is image extraction working? | Yes as a bounded mechanism: a single real pack returned a schema-valid four-field record in 7.6 s. It is **not** accuracy-validated. |
| Biggest technical weaknesses? | Empty ground truth; small 40-row test catalogue; single-name SMS adapter creates review-only generic cases; no real-time regulatory data; packaging NRNs do not overlap the catalogue; live batch exceeded 180 s once. |
| Suitable for backend integration? | **Technically ready for a controlled, read-only trial; NOT APPROVED for production.** `AWAITING_BACKEND_CONFIRMATION` remains `True`. |
| What must backend developers know? | Treat all outputs as observations/suggestions, never authenticity; require explicit confirmation for generic/fuzzy candidates; preserve `UNKNOWN` and `CONFLICT`; do not populate ground truth from engine output; no numeric confidence; contract is proposed only. |

Status labels used below:

- **IMPLEMENTED** - code exists and was inspected.
- **TESTED OFFLINE** - exercised deterministically without network.
- **TESTED LIVE** - exercised with a real Gemini request.
- **PARTIALLY VALIDATED** - some live/deterministic evidence, but not end-to-end acceptance.
- **NOT VALIDATED** - no independent expected result exists.
- **PENDING BACKEND INTEGRATION** - intended for backend use but not wired or approved.

---

## 2. Feature audit table

| Feature | Implementation status | Test coverage | Actual test result | Limitations |
| --- | --- | --- | --- | --- |
| Catalogue load + schema validation (`src/catalogue.py`) | IMPLEMENTED; TESTED OFFLINE | `test_catalogue.py` (10 tests) | 40 rows loaded; missing column, duplicate NRN and missing required value all rejected; source CSV unchanged (SHA-256 `abc95354…514635`) | Deterministic **test** catalogue only; not an authoritative regulatory feed |
| Safe normalisation / exact indexes | IMPLEMENTED; TESTED OFFLINE | `test_catalogue.py` | Safe normalisation verified; registration index used by retrieval; no invented manufacturer (applicant never substituted) | Normalisation is intentionally conservative; formatting variants may still miss |
| Strength vs package-volume parsing | IMPLEMENTED; TESTED OFFLINE | `test_catalogue.py` | `100 ml` parsed as volume, not strength; derived fields come only from existing text | Derived fields are advisory; no external unit ontology |
| SMS parsing and normalisation (`src/message.py`) | IMPLEMENTED; TESTED OFFLINE | `test_message.py` (45 tests, parametrised) | Registration extracted first; messy/Pidgin inputs preserve original text and provenance; `hello` → no usable fields | Single `name` slot; a name can be brand *or* generic, which creates review-only cases; no multi-language model |
| Observation states (`src/observation.py`) | IMPLEMENTED; TESTED OFFLINE | `test_verification.py`, `test_field_compare.py` | `PRESENT`, `MISSING`, `NOT_VISIBLE`, `CONFLICT`, `UNPARSED` preserved with original raw values and provenance; conflicts keep both raw strings | Requires callers to supply structured observations; no automatic OCR-to-conflict detection inside this module |
| Deterministic candidate retrieval (`src/candidate.py`) | IMPLEMENTED; TESTED OFFLINE | `test_candidate.py` (7 tests) | Exact NRN prioritised; unknown NRN never becomes a fuzzy name guess; exact generic returns **all** products; paths merged per product | Registration numbers from packaging have **zero overlap** with the catalogue, so packaging never reaches `MATCH` |
| Fuzzy suggestions (`src/fuzzy.py`) | IMPLEMENTED; TESTED OFFLINE | `test_fuzzy.py` (34 tests) | `Ablept 300 Capusles` → `Ablept 300 Capsules`, score 94.7, requires confirmation; `Amoxicilin Trihydrate` → 3 ambiguous candidates; zero silent wrong selection; short names ask for choice | `CUTOFF=72`, `AMBIGUOUS_GAP=6` are test-calibrated starting values; scores are retrieval hints, not probabilities or identity |
| Seven-field comparison (`src/field_compare.py`) | IMPLEMENTED; TESTED OFFLINE | `test_field_compare.py` (7 tests) | Stable order; NRN exact-only; `MISMATCH` keeps similarity separate; unknown fields stay `UNKNOWN`; conflict propagates originals; strength/dosage form/volume separated | Compares only fields present in the observation; missing catalogue metadata limits corroboration |
| Six-status decision engine (`src/decision.py`) | IMPLEMENTED; TESTED OFFLINE | `test_decision.py` (12 tests) | All six statuses observed in deterministic probes; no confidence/probability/percentage emitted; fuzzy never becomes `MATCH`; `UNPARSED` forces review | `MATCH` requires exact NRN plus corroboration; otherwise `PARTIAL_MATCH`/review is normal, which may surprise users expecting a binary verdict |
| Verification facade + adapters (`src/verification.py`) | IMPLEMENTED; TESTED OFFLINE | `test_verification.py` (5 tests) | SMS, photo and package adapters keep source channel, provenance and unverified status; batch has no forced `MATCH`; contract remains unconfirmed | `verify_photo_result` exists and works, but photo schema has only four fields, so package volume is not extracted |
| Package reconciliation (`src/packaging.py`) | IMPLEMENTED; TESTED OFFLINE | `test_packaging.py` (15 tests) | 22 image rows → 11 reconciled medicines in 2.04 ms; 22 consistent, 27 not visible, 3 indoor-only, 2 daylight-only, 1 conflict (`pack_10` brand); output byte-equal to preserved `package_results.csv` (0 diffs) | Uses preserved OCR records, not fresh images; reconciliation is deterministic, not a validity judgement |
| Ground-truth safety guard (`src/packaging.py`) | IMPLEMENTED; TESTED OFFLINE | `test_ground_truth.py` (3 tests) | `evaluate_ground_truth()` returns `NOT TESTED`, `accuracy_tested=False`, 0 scored / 44 skipped fields; Gemini output never becomes ground truth | Until independent physical-label verification is supplied, **no OCR accuracy percentage can be calculated** |
| Gemini explanation (`src/gemini.py`) | IMPLEMENTED; TESTED OFFLINE + TESTED LIVE (controlled) | `test_gemini.py` (29 tests mocked) + 5 live operations previously recorded | Mock suite covers wording, safety traps, refusals, schema and no-key behaviour; live explanation accepted synthetic findings; live validation status = **PARTIAL** | One expanded live batch hit the 180 s limit; live suite not rerun in full here; never states authenticity |
| Gemini intent extraction (`src/gemini.py`) | IMPLEMENTED; TESTED OFFLINE + PARTIALLY VALIDATED LIVE | `test_gemini.py`, `tests/live/test_live_gemini.py` | Structured `ExactExtraction` enforced; offline demo does not need it; earlier controlled live suite exercised the path | Only invoked when deterministic parsing needs clarification and a client is available; not a general chat parser |
| Gemini image extraction (`src/gemini.py`, `src/photo.py`) | IMPLEMENTED; TESTED OFFLINE + TESTED LIVE (controlled) | `test_photo.py` (4), `test_photo_api_errors.py` (7), live image test | Prompt instructs visible-text-only, `'not visible'`, no guessing, no instruction-following from image; `PhotoFields(extra=forbid)`; one real pack produced schema-valid 4 fields in 7.6 s; UI path 5.0 s; two-image UI compare 4.2 s | Accuracy **NOT TESTED**; brand only in this sample; registration and strength were `not visible`; no package-volume field; rate/latency risk across 22 images |
| Upload validation and API-error sanitisation | IMPLEMENTED; TESTED OFFLINE | `test_photo_api_errors.py`, `test_photo.py` | JPEG/PNG/WebP and 5 MB limit enforced; API errors classified; malformed JSON rejected; failure never fabricates values; no raw body/key leaked | Error detail is intentionally minimal; callers get a status, not raw provider diagnostics |
| Pipeline orchestration (`src/pipeline.py`) | IMPLEMENTED; PENDING BACKEND INTEGRATION | `test_integration.py` (4 tests) | `prepare_lookup`, confirmation gating and `Findings` adaptation work in isolation; contract never invents missing fields | Not wired to any backend; **no approval flag changed** |
| Proposed contract (`src/contracts.py`) | IMPLEMENTED but PROPOSED; PENDING BACKEND INTEGRATION | `test_integration.py`, `test_verification.py` | `Findings` validation rejects invention; `AWAITING_BACKEND_CONFIRMATION = True` unchanged | Must not be treated as an accepted API contract |
| Offline competition demo (`tools/demo.py`) | IMPLEMENTED; TESTED OFFLINE | Manually executed | 8 scenarios produced all six statuses; packaging produced 8 `NO_MATCH` + 3 review; `--live` skip path verified with mock mode | Harness only; does not add engine capability |
| Local interactive tester (`tools/interactive_server.py`, `.html`) | IMPLEMENTED; TESTED OFFLINE + controlled live | HTTP smoke tests of all 7 endpoints; browser DOM + `innerText` check | Sections A-F returned real results; no console errors; live photo and two-image compare succeeded; no key displayed | Localhost only, single-user test tool; not a production UI; two-image live compare costs two requests |

---

## 3. What was actually executed in this stage

Commands and outcomes (all from the project root):

- `python tools/demo.py` - 8 scenarios, all six statuses, packaging 8/3 split.
- `python tools/demo.py --live` with `AI_ML_MOCK=1` - graceful skip, no network.
- Deterministic engine probe - 13 cases plus 11 packaging records; all six statuses observed; 13.87 ms total for the 13 cases, 13.78 ms for the packaging batch.
- Deterministic reconciliation probe - 22 OCR rows, 11 medicines, 2.04 ms, 0 diffs versus preserved results.
- **One** bounded live single-image extraction (`pack_01`, daylight) - schema `VALID`, 7,587.6 ms, fields: brand `Avrocid`, manufacturer `AVRO PHARMA`, registration and strength `not visible`.
- Local tester HTTP smoke tests - all endpoints 200; live UI photo 5,040.5 ms (`ok`, schema valid, engine `NO_MATCH`); live UI two-image compare 4,172.1 ms, all fields consistent, manual review `false`.
- `python -m pytest -q` - see final section for exact result.

No full live suite was run. No API key was read, printed, or written to any file. No protected file was modified.

---

## 4. Known limitations and technical debt

1. **Ground truth is empty.** All four primary fields are 0/11 populated. Accuracy is structurally unmeasurable. Any percentage would be fabricated.
2. **Catalogue is a 40-row test sample.** It is not a complete or authoritative register; absence is not proof of a non-existent product.
3. **Packaging NRNs do not intersect the catalogue.** Correct packaging outcomes are `NO_MATCH` or review, never `MATCH`. This is a data limitation, not a bug.
4. **Single-field SMS adapter.** A generic name typed into the SMS text is stored in `brand_name`, so comparisons can show `brand_name = MISMATCH` while retrieval correctly used it as a name. The decision still retains candidates and asks a human; no candidate is falsely confirmed.
5. **Exact generic names require confirmation** even with one candidate (`MANUAL_REVIEW_REQUIRED`), which is safe but reduces automation.
6. **Four-field image schema.** Package volume is never extracted by the existing implementation and must be displayed separately as "not extracted", never inferred from strength.
7. **Live latency/cost.** One expanded live batch previously stopped at 180 s; the interactive two-image compare issues two requests and is therefore deliberately opt-in.
8. **No backend integration.** `src/contracts.py` is proposed, flags unchanged, no endpoint wiring, no approval.

---

## 5. Integration readiness statement

**IMPLEMENTED:** yes.
**TESTED OFFLINE:** comprehensive (182 passing tests plus deterministic probes).
**TESTED LIVE:** explanation, intent and image extraction paths only, in bounded/synthetic operations; status **PARTIAL**.
**PARTIALLY VALIDATED:** Gemini image extraction mechanism, not its accuracy.
**NOT VALIDATED:** real-world OCR accuracy, authoritative catalogue coverage, end-to-end backend behaviour.
**PENDING BACKEND INTEGRATION:** contract, confirmation flow, and all integration seams.

Recommendation: permit a **read-only, human-in-the-loop backend trial** with synthetic or test data. Do not permit production use, authenticity claims, or autonomous acceptance until ground truth is independently populated and backend confirmation is granted.
