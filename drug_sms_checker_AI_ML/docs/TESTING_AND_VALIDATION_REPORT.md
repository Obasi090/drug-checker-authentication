# TESTING AND VALIDATION REPORT — Drug SMS Checker AI/ML

Date: 19 Nov 2026
Source of truth: the frozen working project, from which this release copy was made.

## 1. Headline result

```text
python -m pytest -q
182 passed, 40 skipped, 0 failed, 2 warnings
```

- **182 passed** — offline deterministic and mocked tests.
- **40 skipped** — opt-in live Gemini tests (`tests/live`), skipped unless `--run-live` is supplied.
- **0 failed**.
- **2 warnings** — third-party deprecations from `anyio` and `google-genai`; not project failures.

Live Gemini validation status: **PARTIAL**. The full live suite has **not** passed and was not run during packaging. Real-world OCR accuracy: **NOT TESTED**. Ground truth remains unverified and blank.

## 2. Offline tests (genuine, deterministic)

| Test module | Collected tests | What it covers |
| --- | ---: | --- |
| `tests/test_message.py` | 45 | SMS parsing, normalisation, registration/name extraction |
| `tests/test_fuzzy.py` | 34 | Fuzzy suggestions, cutoffs, short names, no silent wrong selection |
| `tests/test_gemini.py` | 29 | Explanation wording, safety traps, schema, no-key fallback (mocked) |
| `tests/test_packaging.py` | 15 | Dataset shape, reconciliation statuses, conflicts, manual review |
| `tests/test_decision.py` | 12 | All six statuses, mismatch types, no confidence values |
| `tests/test_catalogue.py` | 10 | CSV validation, indexes, strength/volume parsing |
| `tests/test_candidate.py` | 7 | Retrieval priority, collisions, fuzzy-only candidates |
| `tests/test_field_compare.py` | 7 | Seven-field comparison, conflict propagation |
| `tests/test_photo_api_errors.py` | 7 | API error classification, invalid responses, no fabrication |
| `tests/test_verification.py` | 5 | Facade adapters, no forced packaging match, contract unconfirmed |
| `tests/test_integration.py` | 4 | Message→Findings→explanation, confirmation gating, contract validation |
| `tests/test_photo.py` | 4 | Upload validation, no-key behaviour, template shape |
| `tests/test_ground_truth.py` | 3 | Empty ground truth, skipped fields, no Gemini-as-truth |
| `tests/conftest.py` | - | Live opt-in marker and skip logic |

Total offline collected: **182**. These tests execute with no network and no API key.

## 3. Mocked Gemini tests

`tests/test_gemini.py` (29 tests) and `tests/test_photo_api_errors.py` (7 tests) exercise the Gemini-facing logic with deterministic mocks:

- explanation wording, refusal handling and forbidden authenticity/medical claims;
- response schema shape and `extra="forbid"` behaviour;
- no-key behaviour and safe fallback flags;
- malformed JSON / invalid response rejection;
- API error classification and sanitised `PhotoReadError`;
- confirmation that a failure never fabricates a value.

**Mocked tests validate control flow and safety rules. They are not evidence that the live Gemini service behaved correctly.**

## 4. Genuine live Gemini tests

The opt-in suite at `tests/live/test_live_gemini.py` (40 collected tests) covers explanations, API requests, model support, structured JSON and image input. It is skipped in all offline runs.

Documented live evidence to date:

- earlier controlled operations succeeded for explanation, structured JSON and real-image extraction;
- Stage 5.3 recorded **four successful image submissions across three bounded requests** (single-image direct probe, UI `/api/photo`, and a two-image `/api/compare` pair), all schema-valid;
- one expanded live batch previously stopped at the 180-second limit.

**Live validation remains PARTIAL.** The full live suite has **not** passed and must not be described as passed. No live call was made during Stage 5.5 packaging, and no key was printed or exposed.

## 5. Deterministic performance probes

| Probe | Result |
| --- | --- |
| 13 targeted engine cases | All six decisions observed; 13.87 ms total; slowest 4.544 ms (fuzzy generic with 3 candidates) |
| Packaging batch (11 records) | 8 × `NO_MATCH`, 3 × `MANUAL_REVIEW_REQUIRED`, zero `MATCH`; 13.78 ms |
| 22-row OCR reconciliation | 11 medicines in 2.04 ms; 0 cell differences versus preserved `package_results.csv` |
| Preserved dataset | 40 catalogue rows, 11 medicines, 22 images, 22 image-level OCR rows |
| Manual-review checks | `pack_01`, `pack_04`, `pack_10` require review; `pack_10` retains its brand conflict |

## 6. Ground truth and accuracy

`data/packaging/ground_truth.csv` is preserved with 0/11 populated values for `brand_name`, `registration_number`, `manufacturer` and `strength`. `evaluate_ground_truth()` consequently reports:

```text
status = NOT TESTED
accuracy_tested = False
scored_fields = 0
skipped_fields = 44
accuracy = None
```

No accuracy, precision, recall, success rate or percentage is reported anywhere in this release. OCR values in `ocr_results.csv` and `package_results.csv` are **observations**, not verified ground truth, and must never be copied into `ground_truth.csv`.

## 7. Release-copy validation

After packaging, the extracted copy was re-tested independently in a temporary directory. The result is recorded in `RELEASE_MANIFEST.md`. The original working project was not modified; protected file hashes were reconfirmed before and after packaging.

## 8. Summary status

- **OFFLINE VALIDATION PASSED** — 182 passed, 40 skipped, 0 failed.
- **LIVE GEMINI VALIDATION PARTIAL** — bounded controlled successes only; full suite not passed.
- **MOCKED TESTS PASSED** — safety and control flow only.
- **REAL-WORLD OCR ACCURACY NOT TESTED** — ground truth blank.
- **BACKEND INTEGRATION PENDING APPROVAL** — no integration test exists because no backend exists yet.
