# Project Current State Audit — 19 Nov 2026

## Scope and method

This audit is **read-only for existing source and data**. No Gemini or other external API calls were made, no source files were changed, and no backend was searched for or assumed. The only project file created in this phase is this document.

Reviewed:

- `src/` — `message.py`, `fuzzy.py`, `gemini.py`, `photo.py`, `contracts.py`, `pipeline.py`
- `tests/` — offline suites, opt-in live suite, photo template
- `tools/photo_eval.py`
- `data/test_drugs.csv`
- `data/packaging/ocr_results.csv`, `package_results.csv`, `ground_truth.csv`
- actual image files in `data/packaging/daylight/` and `data/packaging/indoor/`
- `README.md`, `requirements.txt`, `.env.example`, `.gitignore`, and existing `docs/*.md`

Historical test results are reported from the prior verified run; `pytest` was **not** re-run during this audit.

---

## 1. Executive summary

The AI/ML package is **implemented and offline-stable**, but the surrounding photo-data package is **not internally consistent**.

| Area | Actual state |
| --- | --- |
| Offline AI code | Working. Last verified run: `116 passed, 40 skipped, 1 warning`. Warning is an unrelated `anyio`/pytest-10 rename notice. |
| Live Gemini | Activated and partially verified: 4/4 capability probes and a 17-case uninterrupted explanation segment passed. Full 40-item live suite remains blocked by upstream API stalls. No mock/fallback was counted as live. |
| Photo OCR accuracy | **NOT TESTED.** Real pack images now exist, but `ground_truth.csv` verification fields are all empty. Gemini outputs must not be used as ground truth. |
| Packaging dataset | 11 packs × 2 conditions = 22 image-level rows and 22 actual image files. ID sets align across the three packaging CSVs, but there are extraction conflicts, manual-review misflags, placeholder/conflicting filenames, and a 11-vs-12 pack mismatch with the existing template/docs. |
| Backend contract | Still **PROPOSED**. `AWAITING_BACKEND_CONFIRMATION = True` and `ProposedBackendAdapter` remains only a seam. |
| Security | `GEMINI_API_KEY` is in project `.env`, loaded server-side by `load_project_env()` with `override=False`; `.gitignore` excludes `.env`. Value was never printed. |

**Bottom line:** the code should not be changed until the packaging data truth set and schema mismatches are resolved. The highest-risk problem is not model code; it is that the new packaging CSVs look authoritative while containing unresolved conflicts and empty verification fields.

---

## 2. Actual state by component

### 2.1 Source architecture

| Module | Responsibility | Assessment |
| --- | --- | --- |
| `src/message.py` | Deterministic NRN extraction, filler stripping, medical-question detection, name detection. | Conservative and exact-span based. Registration number is extracted before name. Does not infer medicines from symptoms. |
| `src/fuzzy.py` | RapidFuzz matching over approved catalogue; exact-first; distinctive-token gate; confirmation for non-exact results. | Thresholds `CUTOFF=72`, `AMBIGUOUS_GAP=6`, `SHORT_NAME_LENGTH=5` are test-calibrated. Fuzzy results never auto-substitute a medicine. |
| `src/gemini.py` | Explanation, exact-span intent fallback, photo-reading interface, safety guard, mock/fallback. | Bounded model config, schema sanitisation, refusal-aware guard, and fallback for `explain()`/`extract_intent()` are in place. `read_photo()` is less hardened than the other two live paths. |
| `src/photo.py` | Four-field photo extraction, upload validation, no-retention stance. | Safe interface, but its four-field schema does not match the five-field packaging extraction data. Module docstring is now stale because real images exist. |
| `src/contracts.py` | Proposed `Findings` contract, validator, backend seam. | Correctly marked proposed. Unknown backend keys are preserved; missing facts stay `None`. Must remain unconfirmed until backend owner responds. |
| `src/pipeline.py` | `prepare_lookup()` and `explain()` orchestration helpers. | Clean seam. Exact name can proceed; fuzzy candidates require confirmation. No regulatory decisions made here. |

### 2.2 Gemini integration and error handling

Confirmed working design:

- `.env` loaded via `python-dotenv` with `override=False` (host environment wins).
- Default model: `gemini-3.1-flash-lite`; override via `GEMINI_MODEL`.
- Retired/failed models are documented: `gemini-2.5-flash` → 404, `gemini-3.8-flash` → 503 at test time.
- `gemini_response_schema()` removes `additionalProperties` before sending Pydantic schemas to Gemini, avoiding the observed `400 INVALID_ARGUMENT`.
- `ThinkingConfig(thinking_budget=0)` and bounded `HttpOptions` (15 s timeout, 2 attempts, short backoff) reduce hangs.
- `explain()` and `extract_intent()` catch `APIError` and fall back safely; `explain()` records code/status in `safety_action`.
- `assert_reply_safe()` is refusal-aware; safe refusals such as “I cannot say it is genuine” are not treated as claims, while direct and negated claims remain rejected.

Gaps:

- `read_photo()` does **not** catch `APIError` and does **not** call `PhotoFields.model_validate()` itself; it uses `json.loads(response.text)`. `extract_photo_fields()` catches broad exceptions, but the caller only sees `type(exc).__name__` and loses HTTP code/status.
- The `src/gemini.py` module docstring says every public method returns a safe deterministic result when no key is configured; `read_photo()` actually raises `GeminiUnavailable`. Behaviour is acceptable, but the docstring is inaccurate.

### 2.3 Medicine matching

- `data/test_drugs.csv` has 40 reference products with `brand_name`, `generic_name`, `registration_number`, `applicant_name`, `manufacturer`, `source_url` populated as follows: 40/40/40/40/5/40. The five manufacturer values are explicitly verified; blanks are not guessed.
- No duplicate registration numbers or duplicate brand names were found in that 40-row catalogue.
- None of the 11 packaging packs matches a reference catalogue brand or registration number. Visible pack registrations are `04-1436`, `04-1860`, `04-3230`; none appears in `data/test_drugs.csv`.
- Therefore the packaging data cannot currently be cross-validated against the approved catalogue, and the fuzzy matcher is not exercised by these packs.

### 2.4 Photo interface

- `PhotoFields` extracts exactly four fields: `brand_name`, `registration_number`, `manufacturer`, `strength`.
- Upload validation allows JPEG/PNG/WebP, rejects empty and >5 MB inputs.
- Missing values default to lowercase `"not visible"`; no live OCR is enabled without a configured client; accuracy stays `False`.
- `tools/photo_eval.py` remains read-only and prints `REAL-PACK OCR ACCURACY: NOT TESTED` until the template is complete.

Mismatch with the new dataset:

- `ocr_results.csv` records **five** extraction fields: the four above plus `package_volume_separate_from_strength`.
- `ground_truth.csv` has no package-volume column, so volume cannot be verified even if the other fields are filled.
- The CSVs use title case `"Not visible"`, while `PhotoFields` uses lowercase `"not visible"`. There is no normaliser, so consumers must not rely on exact string equality.
- `ocr_results.csv` names the registration column `nafdac_registration_number`; `ground_truth.csv` uses `registration_number`; `PhotoFields` uses `registration_number`.
- `package_results.csv` uses `package_volume_not_strength` while `ocr_results.csv` uses `package_volume_separate_from_strength`.

### 2.5 Packaging CSV integrity

#### Structural checks

| Check | Result |
| --- | --- |
| `ocr_results.csv` rows | 22 |
| `package_results.csv` rows | 11 |
| `ground_truth.csv` rows | 11 |
| Medicine-ID sets | Identical across all three CSVs: `pack_01` … `pack_11` |
| Duplicate `(medicine_id, image_condition)` | None |
| Each pack has daylight + indoor | Yes, for all 11 packs |
| Actual image files | 11 daylight + 11 indoor = 22 files |
| Ground-truth verification fields | `brand_name`, `registration_number`, `manufacturer`, `strength`: **0/11 populated** |
| OCR accuracy computable | **No** |

#### Extraction conflicts between daylight and indoor

| Pack | Conflicting fields | Detail |
| --- | --- | --- |
| `pack_05` | `manufacturer`, package volume | Daylight: `"Not visible"` / empty. Indoor: `"New Healthway Co. Limited"` / `200 ml`. `package_results.csv` adopts both indoor values but sets `manual_review_required=False`. |
| `pack_06` | package volume | Daylight empty; indoor `100 ml`. `package_results.csv` adopts `100 ml` but sets `manual_review_required=False`. |
| `pack_10` | `brand_name`, registration number | Daylight: longer brand including `Two-Layer Tablets` and `04-1860`; indoor: shorter brand and `"Not visible"`. `package_results.csv` keeps daylight brand and reg, but `manual_review_fields=brand_name` only; the registration conflict is not flagged. |
| `pack_11` | registration number | Daylight `04-3230`; indoor `"Not visible"`. `package_results.csv` adopts daylight value but sets `manual_review_required=False`. |

Only `pack_10` is flagged for manual review, and even there the flag is incomplete. `pack_05`, `pack_06`, and `pack_11` should not be presented as conflict-free.

#### Filename and traceability problems

- Actual daylight files are `pack_01.jpeg` … `pack_11.jpeg`. `ocr_results.csv` calls `pack_01` daylight `pack_01.jpg (assumed)`.
- Actual indoor file for `pack_01` is `pack_01..jpeg` (double dot); the CSV says `pack_01 indoor image (filename not supplied)`.
- Most CSV `image_filename` values are descriptive placeholders, not real filenames.
- `pack_04` indoor is marked `pack_04_2.jpeg (described once as pack_04.jpeg; confirm filename)`; the actual indoor file is `pack_04.jpeg`.
- There is no image hash, capture timestamp, extractor/model version, or reviewer field. The CSVs cannot be reproduced or audited back to exact bytes.
- `package_results.csv` contains a historical note that a narrative paired pack_02 indoor data with pack_01. Medicine IDs appear consistent, but the note should be resolved rather than left as narrative ambiguity.

#### Pack-count mismatch

- Packaging datasets and images: **11 packs** (`pack_01`…`pack_11`), 22 captures.
- `tests/photo_test_template.csv`: **12 packs** (`PACK-01`…`PACK-12`), 24 captures, all `pending`.
- `tools/photo_eval.py`, `tests/test_photo.py`, `README.md`, and `docs/AI_ML_*.md` still describe the 12-pack template.
- Decision required: either add the missing `pack_12` images/rows or converge the template, tests, and docs on 11 packs. Do not silently change one side.

### 2.6 Tests

Last verified offline result: `116 passed, 40 skipped, 1 warning`.

| Suite | Coverage | Notes |
| --- | --- | --- |
| `test_message.py` | 45 messy messages | Exact-span NRN handling; no symptom-to-name inference. |
| `test_fuzzy.py` | 32 misspellings + 2 safety assertions | Zero silent wrong selections. |
| `test_gemini.py` | 29 mock/schema/refusal cases | Safety traps run twice. |
| `test_photo.py` | 4 harness/validation cases | Still asserts a 12-pack template and uses a test name implying no real photos exist. |
| `test_integration.py` | 4 contract/pipeline cases | Confirms confirmation gate and no invented fields. |
| `tests/live/` | 40 collected opt-in items | Skipped by default via `--run-live`; synthetic findings only. |

Coverage gaps found:

- No offline test reads `ocr_results.csv`, `package_results.csv`, `ground_truth.csv`, or verifies that CSV filenames map to actual image files.
- No test asserts conflict detection or correct `manual_review_required` values.
- No test guards against accidentally treating an empty ground-truth field as an accuracy result.
- `test_template_has_12_packs_in_two_lighting_conditions()` encodes the stale 12-pack assumption.
- `test_no_real_pack_photos_means_accuracy_not_tested()` is semantically stale now that images exist; the accurate statement is “no populated ground truth means accuracy not tested”.

### 2.7 Docs, security, and boundaries

- `README.md`, `AI_ML_HANDOFF.md`, `AI_ML_PREREQUISITES.md`, and `AI_ML_LIVE_TEST_REPORT.md` accurately describe the earlier state where no pack photos existed. That statement is now false.
- Live report correctly records partial results and the upstream stall; it does not fabricate a complete pass.
- `.env.example` documents `GEMINI_API_KEY`, `GEMINI_MODEL`, and `AI_ML_MOCK=1`.
- `.gitignore` excludes `.env`, `__pycache__/`, `.pytest_cache/`, `.venv/`, and `.playwright-mcp/`.
- No git repository is present in the workspace, so there is no diff history for these uncommitted changes.
- PHP calculator files were previously moved outside the workspace; no backend was found and none was searched for during this audit.

---

## 3. Problems discovered, prioritised

### P0 — Data truth and reporting risk

1. **Ground truth is entirely empty.** Accuracy cannot be computed; any OCR correctness claim would be unsupported.
2. **Daylight/indoor conflicts are not flagged for review** on `pack_05`, `pack_06`, and `pack_11`; `pack_10` is only partially flagged.
3. **11-vs-12 pack mismatch** between packaging data/images and template/tools/tests/docs.
4. **Docs say no real photos exist**, but 22 images are now present. This must be corrected without changing the `NOT TESTED` accuracy status.

### P1 — Schema and API hardening

5. **Photo field schema mismatch:** 4 fields in code vs 5 in extraction CSV; no package volume in code or ground truth.
6. **Field-name/value inconsistency:** `registration_number` vs `nafdac_registration_number`, `Not visible` vs `not visible`, diverging package-volume column names.
7. **`read_photo()` lacks the APIError/validation hardening** already applied to `explain()` and `extract_intent()`; error details are lost by the caller.
8. **No provenance columns** (image hash, reviewer, extractor version) make the CSV results non-reproducible.

### P2 — Test and maintainability debt

9. **No tests validate packaging CSV integrity** or image filename existence.
10. **Stale test names/assertions** encode the old 12-pack/no-photo state.
11. **No linkage between packaging IDs and the 40-product catalogue**, so matching accuracy cannot be evaluated on these packs.
12. **`src/gemini.py` docstring overstates no-key behaviour** for `read_photo()`.

---

## 4. Recommended implementation order (after approval)

No implementation should happen until the user approves this audit. The order below minimises rework.

1. **Decide the canonical pack set.** Choose 11 or 12 packs. If 11, add `pack_12` images and rows or update the template/test/docs/tool wording to 11. Record the decision in `docs/PROJECT_CURRENT_STATE_AUDIT.md` or a new dataset README.
2. **Repair the packaging truth set.** Canonicalise column names and `"not visible"` casing, add missing provenance columns, map every row to an actual filename, resolve daylight/indoor conflicts by human review, and set `manual_review_required`/`manual_review_fields` correctly (`pack_05`, `pack_06`, `pack_10` reg, `pack_11`). Keep `ground_truth.csv` empty only if unverified; explicitly label accuracy `NOT TESTED`.
3. **Align the code/data schema.** Either add package volume to `PhotoFields` and ground truth or remove it from the extraction schema with a documented reason. Add a normaliser for `"Not visible"` and a single registration-field convention.
4. **Harden `read_photo()`.** Catch `APIError`, validate with `PhotoFields.model_validate()`, preserve code/status in error details, and keep bytes in memory only.
5. **Add integrity tests.** Validate ID sets, one daylight + one indoor row per pack, no duplicate pairs, real filename existence, conflict detection, manual-review flags, and a guard that empty ground truth never yields an accuracy score.
6. **Update docs and stale names.** Correct “no real photos” statements, the 11/12 discrepancy, `src/photo.py` docstring, `src/gemini.py` docstring, and `test_no_real_pack_photos_means_accuracy_not_tested`.
7. **Keep the backend seam unchanged** until the backend owner confirms `Findings`. Do not turn `ProposedBackendAdapter` into a second engine.
8. **Optional later, when API is stable:** complete the opt-in live suite with `python -m pytest -q tests/live --run-live -ra`. This is not part of the audit and must not be used to infer pack OCR accuracy.

---

## 5. Explicit non-claims

- No real-pack OCR accuracy has been measured.
- No Gemini output was used as ground truth.
- No source files were modified in this audit phase.
- No external API request was made in this audit phase.
- No backend implementation or contract confirmation was discovered.
- The proposed findings contract remains unconfirmed.

## Post-audit implementation note

The corrections from this audit were implemented after this historical record was written. The current state is documented in:

- `docs/PACKAGING_DATASET_VALIDATION.md`
- `docs/PHOTO_COMPARISON_REPORT.md`
- `docs/GROUND_TRUTH_STATUS.md`

The dataset was standardised on 11 packs; no `pack_12` was invented.
