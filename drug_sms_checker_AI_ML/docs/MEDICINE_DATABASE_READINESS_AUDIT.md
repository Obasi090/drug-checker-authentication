# Medicine Database Readiness Audit — 19 Nov 2026

## Scope and read-only confirmation

This is a **Stage 3 read-only audit** of the standalone AI/ML component for the Drug SMS Checker competition project.

Inspected:

- `data/test_drugs.csv`
- `src/message.py`
- `src/fuzzy.py`
- `src/contracts.py`
- `src/pipeline.py`
- `src/photo.py`
- `src/packaging.py`
- Existing offline and live test files relating to medicine extraction/matching

Not performed:

- No frontend or backend work.
- No external database connection.
- No Gemini or other external AI API call.
- No network request.
- No modification to `data/test_drugs.csv`, source modules, existing tests, `.env`, images, `ground_truth.csv` or any other project data file.
- No implementation of database matching.

Only local read-only Python probes were used to confirm observed matching behaviour. **This report file is the only project file created.**

---

## Executive conclusion

The current dataset is **partially ready** as a small, deterministic test catalogue and as a source for conservative fuzzy name suggestions. It is **not ready** to be treated as an authoritative verification database yet.

What is ready:

- 40 unique medicine brand records.
- 40 unique NAFDAC registration numbers.
- All 40 rows have `brand_name`, `generic_name`, `registration_number`, `applicant_name` and `source_url`.
- A deterministic SMS parser already extracts registration numbers and explicit medicine names.
- A conservative fuzzy matcher already avoids silent substitution and can return multiple candidates.
- Contracts already have fields for brand, generic name, strength, manufacturer, registration number, multiple matches and mismatch records.

What blocks full verification readiness:

- `manufacturer` is populated in only **5 of 40** rows.
- There is **no structured `strength`, `dosage_form`, `medicine_id`, alias, registry-status or manual-review column** in the CSV.
- Strength and dosage form are embedded inconsistently inside `brand_name`.
- Fuzzy scores are `WRatio` similarity scores, **not probabilities or identity proof**.
- Registration numbers are extracted from SMS but are **not indexed or matched locally** against the catalogue.
- An exact generic-name match can collapse to the first catalogue row; for example, `Paracetamol` resolves to `AC-Mol Drops` in a local probe.
- The contracts are still marked `AWAITING_BACKEND_CONFIRMATION = True` and do not declare confidence or manual-review fields.
- Packaging OCR has no adapter into the SMS verification path, and OCR accuracy remains `NOT TESTED`.

**Recommended stage 3 decision:** build the verification engine as a separate, read-only, offline layer that produces explainable candidates and field-level comparisons. Do not promote fuzzy similarity to identity. Do not allow a MATCH verdict unless registration-number or other high-confidence evidence supports it.

---

# A. Database structure

## A.1 File and shape

Dataset inspected: `data/test_drugs.csv`

| Property | Value |
| --- | ---: |
| Total medicine records / data rows | **40** |
| Header row | 1 |
| Total available columns | **6** |
| Columns | `brand_name`, `generic_name`, `registration_number`, `applicant_name`, `manufacturer`, `source_url` |

Fields that are **not present** and must not be assumed:

- `medicine_id` / stable product ID
- `strength`
- `dosage_form`
- `alias`
- `manufacturer_name_normalised`
- `registry_status`
- `alert`
- `manual_review_required`
- `data_as_of`
- field-level provenance timestamps

## A.2 Populated and missing values per column

| Column | Populated | Missing | Completeness | Notes |
| --- | ---: | ---: | ---: | --- |
| `brand_name` | 40 | 0 | 100% | All unique. |
| `generic_name` | 40 | 0 | 100% | Contains repeated and semicolon-separated ingredients. |
| `registration_number` | 40 | 0 | 100% | All match the observed NAFDAC-style format. |
| `applicant_name` | 40 | 0 | 100% | Repeated across many products. Not a reliable manufacturer substitute. |
| `manufacturer` | **5** | **35** | **12.5%** | Main data-quality gap. |
| `source_url` | 40 | 0 | 100% | All unique Greenbook detail URLs. |

## A.3 Duplicate medicine names

| Check | Result |
| --- | --- |
| Exact duplicate `brand_name` | **0** |
| Normalised duplicate `brand_name` | **0** |
| Duplicate `source_url` | **0** |

The 40 brand names and 40 registration numbers are unique, so the catalogue has no obvious duplicate product rows.

### Repeated generic names

Repeated generics are expected because different brands can contain the same active ingredient(s), but they matter for matching.

| `generic_name` | Count |
| --- | ---: |
| `α-β Arteether` | 4 |
| `Paracetamol` | 2 |
| `Tramadol Hydrochloride` | 2 |

### Repeated applicant names

| `applicant_name` | Count |
| --- | ---: |
| `A.C. Drugs Ltd` | 15 |
| `1980 Pharmaceutical Limited` | 3 |
| `Micro Nova Pharmaceuticals Ind Ltd` | 2 |
| `Greenlife Pharmaceutical Limited` | 2 |
| `Accesslife Pharmaceutical Nig Ltd` | 2 |

These are not duplicate records. They show that applicant identity is not product identity.

## A.4 Duplicate NAFDAC registration numbers

| Check | Result |
| --- | --- |
| Exact duplicate `registration_number` | **0** |
| Normalised duplicate `registration_number` | **0** |
| Registration format outliers | **0** |

Observed registration-number prefixes:

| Prefix | Count | Example |
| --- | ---: | --- |
| `A4` | 21 | `A4-101915` |
| `A11` | 9 | `A11-0153` |
| `04` | 5 | `04-0858` |
| `B4` | 4 | `B4-1180` |
| `C4` | 1 | `C4-1202` |

All values follow the same broad pattern: 2–3 alphanumeric prefix characters, a hyphen, then 4–6 digits. The hyphen is part of the real registration number and should be preserved.

## A.5 Records with incomplete information

**35 of 40 rows are incomplete solely because `manufacturer` is blank.**

The only 5 rows with a populated `manufacturer`:

| `registration_number` | `brand_name` | `manufacturer` |
| --- | --- | --- |
| `04-0858` | `10% Dextrose (500/1000 mL)` | `Dana Pharmaceuticals Limited` |
| `B4-1180` | `1980 Azithromycin USP 250 mg Tablets` | `Surmount Laboratories Pvt Ltd` |
| `A4-101915` | `1980 Ceftriaxone 1 g Injection + Water for Injection` | `Anhui Chengshi Pharmaceutical Co., Ltd` |
| `A4-8982` | `Acimox Capsule` | `A.C. Drugs Ltd` |
| `04-1984` | `Actifed Cold Tablets` | `GlaxoSmithKline S.A.E` |

All other fields are populated in all 40 rows. No leading/trailing whitespace anomalies were found in the raw CSV values.

## A.6 Obvious spelling and formatting inconsistencies

No obvious spelling errors were detected in `brand_name` or `registration_number`. The main inconsistencies are structural and formatting-related:

1. **Strength embedded in brand names.**  
   10 of 40 `brand_name` values contain numeric strength text, for example:
   - `Ablept 300 Capsules`
   - `Abther 150 Injection`
   - `Abther 225 Injection`
   - `Aciclovir Cream BP 5% w/w`
   - `Abacavir / Lamivudine Dispersible Tablets 120 mg/60 mg`

   There is no separate `strength` column.

2. **Dosage form embedded in brand names.**  
   38 of 40 brand names contain a form word such as `Tablet`, `Capsule`, `Injection`, `Cream`, `Suspension`, `Drops`, `Emulsion` or `Water for Injection`. There is no separate `dosage_form` column.

3. **Multi-ingredient generics are packed into one string.**  
   10 generic-name values use semicolons, for example:
   - `Clobetasol; Ketoconazole; Neomycin`
   - `Paracetamol; Caffeine`
   - `Dolutegravir (Dolutegravir Sodium); Abacavir; Lamivudine`

4. **Mixed conjunction/punctuation style.**
   - `Abacavir Sulfate & Lamivudine Tablet` uses `&`.
   - `Abacavir, Dolutegravir and Lamivudine Tablets ...` uses `and`.
   - `Abackson Pharmaceuticals Limited,` has a trailing comma in `applicant_name`.

5. **Different scripts for the same concept.**
   - `generic_name` contains `α-β Arteether` using Greek letters.
   - The corresponding `brand_name` is `A-B Arteether Injection` using ASCII hyphens/letters.
   - Current normalisation does not transliterate Greek letters.

6. **Applicant/manufacturer distinction is blurred.**  
   `applicant_name` is complete for all rows but `manufacturer` is mostly blank. Applicant must not be silently copied into manufacturer.

7. **No internal stable identifier.**  
   Registration numbers are currently the best unique key, but the packaging sample uses its own `pack_01`…`pack_11` IDs. No mapping table exists.

---

# B. Medicine matching readiness

Inspected module: `src/fuzzy.py`, supported by `src/message.py`.

## B.1 How names are normalised

Two normalisation layers exist.

### Message normalisation — `normalize()` in `src/message.py`

`normalize()`:

- Applies Unicode NFKC normalisation.
- Converts hyphen-like glyphs `- ‐ ‑ ‒ – — ―` to ASCII `-`.
- Collapses whitespace.
- Strips leading/trailing whitespace.
- Lowercases text.

Example:

```text
"  CHECK   AC-Drex   TABLET  " -> "check ac-drex tablet"
"A4–101970"                    -> "a4-101970"
```

### Fuzzy matching tokens — `distinctive_tokens()` in `src/fuzzy.py`

`distinctive_tokens()`:

- Extracts lowercase alphanumeric tokens with `[a-z0-9]+`.
- Keeps tokens of length 4 or more.
- Keeps 3-character tokens only if they are not purely numeric.
- Drops short numeric tokens such as `150` or `300` from the distinctive-token set.

This is used as a safety gate: a candidate alias must share at least one distinctive token with the query before `WRatio` scoring is applied.

Important limitation: this gate is not a substitute for structured strength parsing. numbers of 4+ digits are treated as distinctive, but 3-digit strengths are not.

## B.2 Spelling mistakes

Spelling forgiveness is implemented with `rapidfuzz`:

- Scorer: `fuzz.WRatio`
- Candidate search: `process.extract`
- `CUTOFF = 72`
- `AMBIGUOUS_GAP = 6`
- `SHORT_NAME_LENGTH = 5`

Behaviour:

- Exact normalised alias match: `status="exact"`, score `100.0`, no confirmation required.
- Non-exact fuzzy candidate: `status="suggest"` or `"ambiguous"`, `requires_confirmation=True`.
- Below cutoff or no distinctive token: `status="clarify"`.
- Fuzzy corrections are never auto-applied.

This is deliberately conservative and appropriate for the current stage.

However, `Candidate.score` is a fuzzy string-similarity score. It is **not** a calibrated probability and must not be described as confidence that two medicines are the same product.

## B.3 Partial medicine names

Partial names are only indirectly supported.

Local read-only probes:

| Query | Result |
| --- | --- |
| `Ablept 300 Capsules` | exact -> `Ablept 300 Capsules` |
| `Ablept 300` | suggest -> `Ablept 300 Capsules`, score 90.0 |
| `Ablept` | suggest -> `Ablept 300 Capsules`, score 90.0 |
| `Acimox` | suggest -> `Acimox Capsule`, score 90.0 |
| `Acimox Cap` | suggest -> `Acimox Capsule` |
| `ab` | ambiguous or clarify |

So a sufficiently long partial name may produce a suggestion, but there is no dedicated partial-name grammar, no required-field model and no rule saying which missing parts are acceptable. Short names are forced into ambiguity/clarification.

## B.4 Strength consideration

There is **no structured strength matching**.

Strength appears only inside `brand_name` strings. Fuzzy matching may incidentally consider numeric tokens because the whole brand string is scored, but there is no parser that extracts `250 mg`, `1 g`, `100 ml`, `5% w/w` or combination strengths.

Read-only probe:

| Query | Observed result |
| --- | --- |
| `1980 Azithromycin 250 mg Tablets` | suggest -> `1980 Azithromycin USP 250 mg Tablets`, score 95.0 |
| `1980 Azithromycin 500 mg Tablets` | top candidate still `1980 Azithromycin USP 250 mg Tablets`, score 91.2, status `ambiguous` |

This is a safety concern: the catalogue does not contain 500 mg, but the matcher still ranks the 250 mg product first. The ambiguity gap happens to flag this example, but that is incidental, not a reliable strength rule.

Package volume must also remain separate from strength. `src/packaging.py` already enforces that separation for OCR; the future database engine must preserve it.

## B.5 Manufacturer consideration

Manufacturer is not used for matching.

- `CatalogueEntry` has a `manufacturer` field.
- `Candidate` does **not** expose manufacturer.
- `DrugCatalogue` builds aliases only from `brand_name` and `generic_name`.
- No manufacturer comparison exists.
- No manufacturer mismatch detection exists.

Given that only 5/40 rows have manufacturer data, manufacturer cannot currently be a reliable matching criterion. It can only be a supporting comparison field where both observed and catalogue values are present.

## B.6 Registration-number consideration

Registration numbers are handled in `src/message.py`, not in `src/fuzzy.py`.

Capabilities:

- `find_registration_number()` extracts the exact original span.
- The regex accepts observed hyphen glyph variants.
- It requires a hyphen between prefix and digits.
- It preserves the original span for traceability.
- `prepare_lookup()` sends the extracted number directly to the lookup seam as `lookup_type="registration_number"`.

Limitations:

- `DrugCatalogue` does not index registration numbers.
- `suggest()` does not match on registration numbers.
- There is no local registration-number validation against `test_drugs.csv`.
- There is no registration-number mismatch logic.

Read-only probe:

```text
suggest("04-0858", catalogue) -> status="clarify", no candidates
prepare_lookup("check 04-0858", catalogue) -> stage="ready", lookup_type="registration_number", lookup_query="04-0858"
```

The pipeline can pass a registration number onward, but the standalone component cannot yet say whether that number exists in the catalogue.

## B.7 Ambiguous matches

Ambiguity handling exists in `suggest()`:

- If the normalised query has fewer than 5 characters after spaces are removed, result is `ambiguous` or `clarify`.
- If more than one candidate exists and the top-two `WRatio` scores differ by less than `AMBIGUOUS_GAP = 6`, result is `ambiguous`.
- Ambiguous results include up to 3 candidate options and require confirmation.

Example read-only probe:

```text
"Abther Injection" -> ambiguous
  1. Abther 150 Injection  (95.0)
  2. Abther 225 Injection  (95.0)
  3. 1980 Ceftriaxone 1 g Injection + Water for Injection (85.5)
```

This is good conservative behaviour, but the third candidate shows that scoring can still include weak, unrelated products because of shared dosage-form tokens.

## B.8 Multiple possible candidates

Yes, the matching module can return multiple candidates:

```python
Suggestion.candidates: list[Candidate]
```

Observed behaviour:

- Exact alias match: 1 candidate.
- `suggest`: up to 3 candidates, with the first presented as “Did you mean ...?”.
- `ambiguous`: up to 3 candidates, with a “choose the product” prompt.
- Deduplication key: `(brand_name, registration_number)`.

`process.extract()` initially asks for up to 5 aliases, but the returned `Suggestion` is capped at 3.

## B.9 Important observed risks

1. **Exact generic-name matching collapses duplicates.**  
   `suggest("Paracetamol", catalogue)` returns exact match to `AC-Mol Drops` because `entry_for_alias()` returns the first matching alias. `Paracetamol` appears in 2 generic rows, and similar generic collisions exist.

2. **Fuzzy result can be a different product with the same dosage form.**  
   `suggest("Acimox Suspension", catalogue)` suggests `Acepol Suspension`. Confirmation is required, but this must not be treated as identity evidence.

3. **No field-level verification exists.**  
   The matcher finds name candidates; it does not compare strength, manufacturer, registration number or packaging volume.

---

# C. Existing pipeline

Inspected modules: `src/message.py` and `src/pipeline.py`.

## C.1 Current SMS flow

An incoming SMS currently moves through this path:

1. `prepare_lookup(text, catalogue, client=None)` receives the SMS.
2. `parse_message()` derives a `MessageIntent`.
3. If the message needs clarification and an available Gemini client is supplied, `client.extract_intent(text)` may fill name/registration fields. This audit did not call Gemini.
4. If a registration number exists:
   - `stage="ready"`
   - `await_confirmation=False`
   - `lookup_query=<registration number>`
   - `lookup_type="registration_number"`
5. If a name exists:
   - `suggest()` is called.
   - Exact name match: `stage="ready"`, lookup query is the candidate registration number if available, otherwise the matched name.
   - Fuzzy or ambiguous name: `stage="await_confirmation"`, no lookup query is emitted.
6. If neither name nor registration number exists:
   - `stage="clarify"`
7. Separately, `explain()` adapts a findings payload into `Findings` and asks Gemini, or the deterministic mock, to produce an explanation.

## C.2 What information is extracted

From SMS:

- Original text.
- Normalised text.
- Registration number, when present.
- Explicit medicine name, when present.
- Intent: `lookup`, `medical_question` or `clarify`.
- `medical_question` boolean.
- `needs_clarification` boolean.
- `extracted_by`: `deterministic`, `gemini` or `none`.
- Notes for traceability.

The parser deliberately does **not** convert symptoms or context into a medicine name.

## C.3 What information is missing

From SMS parsing:

- Strength is not extracted as a separate field.
- Manufacturer is not extracted as a separate field.
- Dosage form is not extracted as a separate field.
- Generic name is not extracted as a separate field.
- No field-level confidence is produced.
- No evidence/provenance record is produced beyond `extracted_by` and `notes`.
- No candidate-by-field comparison is produced.
- No manual-review flag is produced.

From the database path:

- No local registration-number lookup.
- No local verification engine.
- No structured strength/manufacturer comparison.
- No stable product ID.

## C.4 Where medicine matching currently happens

Only one local matching step exists:

```python
suggest(intent.name, catalogue)
```

inside `prepare_lookup()`.

This is **candidate suggestion**, not verification. It does not decide whether the SMS description and database record refer to the same medicine.

Registration numbers bypass local matching entirely and are passed to the backend seam.

## C.5 What the pipeline currently returns

`prepare_lookup()` returns `PreparedLookup`:

| Field | Meaning |
| --- | --- |
| `intent` | Parsed `MessageIntent` |
| `suggestion` | Optional `Suggestion` from fuzzy matching |
| `stage` | `ready`, `await_confirmation` or `clarify` |
| `await_confirmation` | Whether user confirmation is required before lookup |
| `lookup_query` | Value to send to backend, if ready |
| `lookup_type` | Usually `registration_number` or `name` |

`explain()` returns an `Explanation` from the Gemini/mock explanation layer.

There is no `VerificationResult`, no six-way status label and no field-level comparison object.

## C.6 Can packaging OCR results enter the same process?

Not today, but the building blocks exist.

Available OCR-side pieces:

- `src/photo.py` exposes `PhotoFields` with exactly four fields:
  - `brand_name`
  - `registration_number`
  - `manufacturer`
  - `strength`
- `src/packaging.py` reconciles daylight/indoor records into `package_results.csv` with statuses:
  - `CONSISTENT`
  - `DAYLIGHT_ONLY`
  - `INDOOR_ONLY`
  - `NOT_VISIBLE`
  - `CONFLICT`
- `src/packaging.py` also provides `evaluate_ground_truth()`, but ground truth is empty and OCR accuracy is `NOT TESTED`.

Missing bridge:

- No adapter converts `PhotoResult` or `package_results.csv` rows into the same observation/candidate/verification model used by SMS.
- `PreparedLookup` has no OCR or packaging fields.
- Contracts have no field-level OCR provenance or manual-review flag.
- Packaging registration numbers in this sample do not overlap with `test_drugs.csv` (`04-1436`, `04-1860`, `04-3230` are absent), so cross-validation against this catalogue is not currently possible.

A future verification engine can accept both channels, but it must keep source provenance distinct and must not treat OCR output as ground truth.

---

# D. Contract readiness

Inspected module: `src/contracts.py`.

Status marker:

```python
AWAITING_BACKEND_CONFIRMATION = True
```

The contract is explicitly proposed, not confirmed. `Findings` and related models use `extra="allow"`, so unknown keys are preserved, but that does not mean new keys are agreed or safe to rely on.

## D.1 Existing data structures

| Structure | Purpose | Important fields |
| --- | --- | --- |
| `DrugMatch` | One matched registry record | `reg_number`, `brand_name`, `generic_name`, `manufacturer`, `strength`, `dosage_form`, `registry_status`, `source` |
| `DrugAlert` | Alert/notice record | `alert_type`, `alert_date`, `reason`, `source_link`, `resolved_date`, `matched_by` |
| `Mismatch` | Provisional field mismatch | `field`, `expected`, `observed` |
| `Findings` | Backend response envelope | `query`, `query_type`, `status`, `matches`, `alerts`, `mismatches`, `data_as_of` |
| `BackendLookup` | Protocol seam | `check(query, query_type)` |
| `ProposedBackendAdapter` | Validates backend payload | wraps a lookup callable and calls `adapt_findings()` |

`Status` is currently:

```text
found | multiple | not_found | invalid
```

## D.2 Compatibility with required verification concepts

| Requirement | Current support | Assessment |
| --- | --- | --- |
| Extracted medicine name | `MessageIntent.name`; `DrugMatch.brand_name` / `generic_name` | Supported as a value, not as a verified identity. |
| Strength | `DrugMatch.strength` exists | Contract field exists, but the catalogue has no structured strength to populate it reliably. |
| Manufacturer | `DrugMatch.manufacturer` exists | Contract field exists, but dataset is 35/40 blank. |
| NAFDAC registration number | `DrugMatch.reg_number`; `Findings.query_type` | Supported, but field name differs from dataset (`registration_number`) and OCR (`nafdac_registration_number`). A mapping rule is needed. |
| Multiple possible database matches | `Findings.status="multiple"` and `matches: list[DrugMatch]`; `Suggestion.candidates` | Supported structurally. |
| Match confidence | No declared field in `DrugMatch` or `Findings`; only `Candidate.score` exists in fuzzy layer | **Not contract-ready.** Fuzzy score must not be presented as confidence without calibration and backend agreement. |
| Field-level comparison results | `Mismatch` has `field`, `expected`, `observed`; `Findings.mismatches` list | Partially supported. No declared comparison status, evidence, source or manual-review reason. |
| Manual review requirements | No declared field in `Findings`; packaging has separate `manual_review_required` | **Not contract-ready.** Needs backend agreement before adding a standard field. |

## D.3 Status vocabulary gap

The required stage-3 outcome labels are:

```text
MATCH
PARTIAL_MATCH
MISMATCH
NO_MATCH
INSUFFICIENT_INFORMATION
MANUAL_REVIEW_REQUIRED
```

The current `Findings.status` vocabulary is:

```text
found
multiple
not_found
invalid
```

There is no one-to-one mapping, and no place for confidence or manual-review reason. A translation layer will be needed after backend confirmation. Do not silently reinterpret `found` as `MATCH`.

## D.4 Contract decision

The existing contracts are a **reasonable transport seam** but not a complete verification contract.

They can carry many of the facts. They do not yet define:

- verification status vocabulary,
- confidence,
- field-level comparison statuses,
- provenance/source channel for each observed field,
- manual-review reason,
- reviewed-by/reviewed-at,
- distinction between fuzzy candidate score and final match confidence.

No contract changes were made in this audit.

---

# E. Test coverage

Existing relevant test files:

- `tests/test_message.py`
- `tests/test_fuzzy.py`
- `tests/test_integration.py`
- `tests/test_photo.py`
- `tests/test_packaging.py`
- `tests/test_ground_truth.py`
- `tests/test_photo_api_errors.py`
- `tests/live/test_live_gemini.py`

## E.1 Coverage matrix

| Required case | Covered? | Evidence / gap |
| --- | --- | --- |
| Exact medicine name matches | **Yes** | `test_fuzzy.py` includes exact/case-normalised names such as `Actinac 100 Tablets`, `Actifed COLD TABLETS`, `AC MOL DROPS`; exact normalised alias returns score 100. |
| Misspelled medicine names | **Yes** | 32 misspelling cases plus `test_zero_silent_wrong_selection()` and short-name check. Fuzzy corrections always require confirmation unless exact. |
| Partial medicine names | **Partial** | `Acimox Cap`, `ema-500 Tablets` and short `ab` are covered, but there is no systematic partial-name model or test suite for expected partial behaviour. |
| Similar medicine names | **Partial** | Typo variants and dosage-form traps are present, but no explicit pairwise test proves that similar distinct products are separated by field evidence. |
| Different strengths of the same medicine | **Not adequately** | `Abther 150 Injection` and `Abther 225 Injection` are separate exact cases, but no test proves they cannot be confused. Local probe showed `1980 Azithromycin 500 mg Tablets` still ranks the 250 mg product first. |
| Manufacturer mismatches | **No** | Manufacturer is not used in candidate generation, not exposed in `Candidate`, and no catalog-vs-observation comparison test exists. |
| Registration number mismatches | **No** | Tests cover extraction format and a fake backend payload, but no local catalogue registration-number lookup or mismatch verdict. |
| Multiple possible matches | **Partial** | Ambiguous and short-name cases exist, but no deterministic test asserts candidate count, ranking policy, score-gap behaviour and prompt content for a known multi-candidate product family. |
| Missing information | **Yes, for current components** | `test_message.py` covers empty/whitespace/`check`/malformed NRNs; `test_photo.py` covers NOT TESTED; `test_ground_truth.py` covers empty ground truth. No verification-engine-level missing-field tests exist yet. |
| No database match | **Partial** | `status="clarify"` and `empty_catalogue` paths exist; `test_zero_silent_wrong_selection()` checks a trap. There is no explicit real-catalogue no-match test, and `Acimox Suspension` currently suggests a different product rather than returning no match. |

## E.2 Existing test strengths

- Exact spans are preserved in `MessageIntent.original`.
- Registration-number extraction respects real observed formats.
- Medical questions are kept separate from lookup queries.
- Fuzzy suggestions never auto-substitute a non-exact candidate.
- Ambiguous/short queries request clarification.
- Packaging reconciliation tests cover 11 packs, 22 captures, all five reconciliation statuses, package-volume separation and the single `pack_10` conflict.
- Ground-truth tests prevent accuracy claims when verification fields are empty.
- Contract tests prevent fabricated missing fields and reject invalid payloads.

## E.3 Missing test cases for stage 3

Add only when implementation is authorised:

1. Exact registration-number lookup against a local in-memory catalogue index.
2. Unknown registration number must produce `NO_MATCH` or `INSUFFICIENT_INFORMATION`, never a fuzzy name guess.
3. Registration-number mismatch when name matches but number differs.
4. Strength extraction and comparison:
   - `250 mg` vs `250 mg`
   - `250 mg` vs `500 mg`
   - `100 ml` volume vs `100 mg` strength must not compare equal.
5. Distinct products differing only by strength, especially `Abther 150 Injection` vs `Abther 225 Injection`.
6. Manufacturer present/present equal, present/present different, present/missing, missing/missing.
7. Manufacturer must not be inferred from `applicant_name`.
8. Generic-name collision test: `Paracetamol` must not arbitrarily collapse to one brand without confirmation.
9. Multiple-candidate test asserting all returned candidates, scores, order and `requires_confirmation=True`.
10. No-match test with a well-formed but absent name and registration number.
11. Insufficient-information tests: empty SMS, strength-only SMS, unreadable OCR-only input.
12. Conflict tests where SMS and packaging disagree on the same field.
13. OCR provenance test: OCR output is an observation, never ground truth.
14. Manual-review tests for conflict, low confidence, missing fields and OCR `CONFLICT`.
15. Six-way outcome mapping tests for all required statuses.
16. Contract round-trip tests for any newly agreed confidence/manual-review fields.
17. Calibration tests proving thresholds are justified, not guessed.

---

# F. Identified limitations

## F.1 Data limitations

1. **Manufacturer is mostly missing.**  
   35/40 rows cannot support manufacturer comparison.

2. **No structured strength or dosage form.**  
   strength and form are embedded in free-text brand names. This makes exact comparison unreliable.

3. **No stable product identifier.**  
   Registration numbers are unique in this sample, but packaging uses different IDs and no mapping exists.

4. **No aliases/synonyms.**  
   Misspellings are handled generically, but there is no curated alias list for known brand variants, abbreviations or local names.

5. **Generic-name collisions are unresolved.**  
   Repeated generics can map to multiple brands; exact generic matching currently selects the first alias.

6. **Multi-ingredient generics are unparsed.**  
   Semicolon-separated values are single strings, not structured ingredient lists.

7. **Applicant is not manufacturer.**  
   Filling missing manufacturer values from `applicant_name` would be an unsupported inference.

8. **Small catalogue.**  
   40 records are suitable for deterministic offline tests, not for production-level coverage.

9. **No registry-status or alert data in this CSV.**  
   `source_url` is provenance only; it does not provide `registry_status` or alerts.

10. **No overlap with packaging sample.**  
   Packaging registration numbers `04-1436`, `04-1860` and `04-3230` are not in this catalogue, and no packaging brand names match catalogue brand names. Cross-dataset verification cannot be demonstrated with the current sample.

## F.2 Algorithm limitations

1. **Fuzzy similarity is not identity.**  
   `WRatio` score is a string-similarity measure, not a probability.

2. **No strength parsing or strength-aware gating.**  
   A wrong-strength product can remain a top candidate.

3. **Dosage-form tokens inflate similarity.**  
   Shared `Injection`, `Suspension`, `Capsule` etc. can pull unrelated products into candidate lists.

4. **No manufacturer or registration-number candidate search.**  
   Candidate generation is brand/generic-name only.

5. **Cutoffs are test-calibrated only.**  
   `CUTOFF=72` and `AMBIGUOUS_GAP=6` are justified against current spelling tests, not against medicine-identity verification outcomes.

6. **No final verification decision layer.**  
   The current code suggests candidates; it does not decide MATCH/MISMATCH/etc.

## F.3 Contract and integration limitations

1. Proposed contract still awaits backend confirmation.
2. Six required outcome labels are not represented.
3. No declared confidence field.
4. No declared manual-review field.
5. Field-level mismatch shape is provisional.
6. No source-channel or provenance model per observed field.
7. No adapter from packaging OCR/SMS observations into one verification request.

## F.4 Safety limitations

- Real-pack OCR accuracy remains `NOT TESTED` because `ground_truth.csv` is empty.
- OCR observations must remain editable/confirmable and must never be used as expected values.
- A name-only fuzzy match must never become a regulatory claim.
- Missing data must remain missing; no guessed manufacturer, strength or registration number.

---

# G. Recommended architecture

The recommended next-stage design is a **separate read-only verification layer** inside the standalone AI/ML component. It should sit after existing SMS parsing and packaging reconciliation, and before any backend contract mapping.

Do not modify `src/message.py`, `src/fuzzy.py`, `src/contracts.py` or `data/test_drugs.csv` as part of the first implementation slice unless a separate approved change is made.

## G.1 Proposed modules

```text
src/catalogue.py        read-only loader, validation, derived in-memory fields
src/observation.py      common input model for SMS and packaging OCR observations
src/candidate.py        candidate generation and explainable evidence
src/field_compare.py    field-level comparison rules
src/confidence.py       scoring policy and threshold evaluation
src/decision.py         six-way outcome decision
src/findings_mapper.py  optional mapping into proposed Findings contract
```

## G.2 Common observation model

Both SMS and packaging should produce the same logical observation shape:

| Field | Purpose |
| --- | --- |
| `source_channel` | `sms`, `daylight_ocr`, `indoor_ocr`, `consolidated_ocr` |
| `brand_name` | Raw observed value |
| `generic_name` | Only when independently present |
| `registration_number` | Raw observed value |
| `manufacturer` | Raw observed value |
| `strength` | Raw observed value, structured when possible |
| `dosage_form` | Derived/observed only when supported |
| `package_volume` | Separate from strength |
| `field_status` | `PRESENT`, `MISSING`, `NOT_VISIBLE`, `CONFLICT` per field |
| `provenance` | Source file/message span/capture ID |
| `accuracy_tested` | False unless independent ground truth exists |

Packaging must carry forward the existing reconciliation statuses from `src/packaging.py`.

## G.3 Candidate generation

Use multiple independent retrieval paths:

1. Exact normalised registration number.
2. Exact normalised brand name.
3. Exact normalised generic name, but preserve all matches instead of first-match collapse.
4. Fuzzy brand/generic candidates using existing `suggest()` policy.
5. Optional packaging brand candidate path when OCR is enabled.

Each candidate must carry evidence, for example:

```text
matched_by = registration_number_exact
matched_value = B4-9460
evidence_score = ...
fuzzy_score = separate, if used
```

Do not merge fuzzy score and identity confidence into one unexplained number.

## G.4 Field-level comparison

Recommended comparison rules:

| Field | Rule |
| --- | --- |
| Registration number | Normalise hyphen glyphs and case; otherwise require exact value. Never fuzzy-match a registration number. |
| Brand name | Normalise case, punctuation and whitespace; fuzzy similarity is supporting evidence only. |
| Manufacturer | Compare only when both sides are populated. Treat missing as unknown, not equal. |
| Strength | Parse value + unit separately; compare numerically and by unit. Keep package volume separate. |
| Generic name | Supportive evidence; repeated generics require candidate disambiguation. |
| Dosage form | Supportive evidence only. |
| Package volume | Separate metadata; never compared as strength. |

Field comparison output should preserve both original values and a status. It should not invent a value for a missing field.

## G.5 Confidence scoring

Confidence must be explainable and component-based, not a raw fuzzy score.

Suggested evidence hierarchy:

1. Exact registration number: strongest evidence.
2. Exact brand name plus consistent strength/registration: strong evidence.
3. Fuzzy brand name: supporting evidence requiring confirmation.
4. Generic name: weak/supporting evidence because of collisions.
5. Manufacturer: supporting evidence only when populated on both sides.
6. Image OCR: observation requiring confirmation; accuracy currently NOT TESTED.

Rules:

- Missing fields reduce confidence; they do not become matches.
- Conflicts reduce confidence and usually trigger manual review.
- Fuzzy score must be labelled `similarity_score`, not `confidence`.
- Thresholds must be chosen by tests using known cases, not guessed at demo time.
- A name-only fuzzy match can never produce `MATCH` alone.

## G.6 Six-way decision policy

Proposed meaning of the required statuses:

| Status | Proposed rule |
| --- | --- |
| `MATCH` | One unique candidate with high-confidence evidence, normally exact registration number or exact brand plus no conflicting fields. |
| `PARTIAL_MATCH` | One plausible candidate, but some supporting fields are missing or only weakly confirmed; no conflicts. |
| `MISMATCH` | A strong candidate is identified, but one or more observed fields directly conflict with the catalogue value. |
| `NO_MATCH` | Input is sufficient to search, but no viable catalogue candidate exists. |
| `INSUFFICIENT_INFORMATION` | Too few usable fields were supplied to identify or exclude a product. |
| `MANUAL_REVIEW_REQUIRED` | Genuine conflict, multiple close candidates, OCR conflict, missing critical evidence or confidence below threshold. |

Important distinction:

- `NO_MATCH` = enough evidence to search, nothing found.
- `INSUFFICIENT_INFORMATION` = not enough evidence to decide.
- `MISMATCH` = product appears identified but at least one field conflicts.
- `PARTIAL_MATCH` = likely identity, incomplete verification.

## G.7 Contract mapping

After backend confirmation, map internal results into `Findings`:

- `matches` <- ranked candidates.
- `mismatches` <- field comparison rows.
- `status` <- agreed mapping from the six-way internal status.
- `query` / `query_type` <- original lookup request.
- `data_as_of` <- trusted backend metadata, never invented.

Do not add confidence/manual-review keys to the shared contract without backend agreement. If needed immediately, keep them in the internal result model and pass them through as explicitly named extra keys only after confirmation.

---

# H. Numbered implementation plan for the next stage

No implementation is authorised yet. This is the proposed order after approval.

1. **Confirm catalogue ownership and schema.**  
   Decide whether `data/test_drugs.csv` is the approved v1 catalogue. Confirm that no fields may be added yet. Define read-only loading rules.

2. **Define the internal verification models.**  
   Add `MedicineObservation`, `CatalogueProduct`, `CandidateEvidence`, `FieldComparison`, `ConfidenceBreakdown` and `VerificationResult`. Keep these separate from backend `Findings`.

3. **Build the read-only catalogue loader.**  
   Parse all six existing columns, validate registration-number format, assign runtime IDs, and keep `None`/blank values missing. Do not write back to the CSV.

4. **Derive structured fields in memory.**  
   Parse embedded strength and dosage form from brand names where possible. Store parse status and raw text. Never overwrite the source value.

5. **Build exact indexes.**  
   Add normalised brand, generic and registration-number indexes. Registration number must be exact-only after hyphen/case normalisation.

6. **Fix generic-name ambiguity.**  
   Ensure an exact generic name returns all matching products, not the first alias. `Paracetamol` must become multiple candidates or a clarification case.

7. **Add the observation adapters.**  
   - SMS: wrap `MessageIntent`.
   - Packaging: wrap `PhotoFields` and `package_results.csv` rows, preserving `CONSISTENT`, `DAYLIGHT_ONLY`, `INDOOR_ONLY`, `NOT_VISIBLE`, `CONFLICT` and manual-review flags.

8. **Implement candidate generation.**  
   Combine exact registration, exact brand, exact generic and existing fuzzy candidates. Deduplicate by product ID/registration number and retain evidence for each retrieval path.

9. **Implement field-level comparison.**  
   Start with registration number, brand name, strength, manufacturer and package volume. Keep raw values. Treat missing as unknown. Do not infer manufacturer from applicant.

10. **Implement confidence scoring.**  
    Use component scores and documented weights. Store fuzzy similarity separately from final confidence. Add explanation strings for every score component.

11. **Implement the six-way decision layer.**  
    Apply the rules in section G.6. Make conflict and missing-critical-evidence paths default to `MANUAL_REVIEW_REQUIRED` or `INSUFFICIENT_INFORMATION`.

12. **Agree backend contract extensions.**  
    Ask backend owners to confirm status mapping, confidence field, manual-review field and richer field-comparison structure. Keep `AWAITING_BACKEND_CONFIRMATION = True` until confirmed.

13. **Add the contract mapper only after confirmation.**  
    Map internal verification results into `Findings` without inventing missing fields. Preserve `matches` and `mismatches`.

14. **Add the missing offline tests from section E.3.**  
    Prioritise registration mismatch, strength mismatch, manufacturer missing/conflict, generic collision, multiple candidates, no-match, insufficient information and all six outcome labels.

15. **Calibrate thresholds with test fixtures.**  
    Record why each cutoff is chosen. Re-run the full offline suite after each threshold change.

16. **Keep OCR isolated until ground truth exists.**  
    Packaging OCR may produce observations and manual-review flags only. Do not calculate or claim OCR accuracy until `ground_truth.csv` is independently populated.

17. **Run the full offline suite and document results.**  
    Expected standard command:

    ```powershell
    python -m pytest -q
    ```

    Report pass/skip counts and any third-party warnings. Do not weaken or skip existing tests.

18. **Only then consider backend/web integration.**  
    The standalone engine must be stable, explainable and fully tested before any endpoint, UI or external database work begins.

---

## Final readiness decision

| Area | Readiness |
| --- | --- |
| Dataset as deterministic test catalogue | **Ready** |
| Dataset as authoritative verification database | **Not ready** |
| SMS extraction | **Ready for current scope** |
| Fuzzy suggestion | **Ready as candidate generation only** |
| Registration-number local matching | **Not ready** |
| Strength/manufacturer verification | **Not ready** |
| Multiple candidates | **Partially ready** |
| Confidence scoring | **Not ready** |
| Field-level comparison | **Not ready in verification sense** |
| Manual-review decisions | **Only in packaging layer; not generalised** |
| Contract as proposed transport seam | **Partially ready** |
| Contract as final verification contract | **Not ready / awaiting backend confirmation** |
| Packaging OCR into same verification process | **Not connected; planned** |

**Bottom line:** proceed only with an offline, read-only verification-engine design that treats fuzzy matching as candidate generation, preserves missing values, separates package volume from strength, requires confirmation for uncertain cases, and deliberately maps to `MATCH`, `PARTIAL_MATCH`, `MISMATCH`, `NO_MATCH`, `INSUFFICIENT_INFORMATION` and `MANUAL_REVIEW_REQUIRED`.
