# HANDOFF SUMMARY — Drug SMS Checker AI/ML

For: backend development team
Date: 19 Nov 2026
Component status: **IMPLEMENTATION COMPLETE · OFFLINE VALIDATION PASSED · LIVE GEMINI VALIDATION PARTIAL · BACKEND INTEGRATION PENDING APPROVAL**

## What exactly has been built?

A standalone Python AI/ML layer that reads an SMS or a package photo, matches the described medicine against a local 40-record test catalogue, compares seven fields, and returns one of six conservative decisions. It also provides Gemini-based explanations and four-field package-image extraction, deterministic daylight/indoor reconciliation, and a localhost tester. The engine is frozen; no backend code or API endpoint exists yet. `src/contracts.py` is a **PROPOSED** interface, not an approved contract.

## What can the component currently do?

- Parse SMS text, extracting registration number first, otherwise a name, while preserving the original message and provenance.
- Load and validate the catalogue; perform exact registration, brand and generic lookups; retain all products on generic-name collisions.
- Produce conservative fuzzy suggestions with scores that always require confirmation.
- Represent missing, unreadable, unparsed and conflicting values as distinct states.
- Compare registration, brand, generic, manufacturer, strength, dosage form and package volume; keep volume separate from strength.
- Reconcile 22 preserved OCR rows into 11 packaging records offline, preserving both raw image values.
- Call Gemini for bounded explanations and four-field image extraction, with schema validation, sanitised errors and safe fallbacks.
- Run 182 offline tests, an 8-scenario demo, and the interactive tester.

## Main inputs and outputs

| Input | Entry point | Output |
| --- | --- | --- |
| SMS text | `observation_from_sms_text(...)` → `VerificationEngine.verify()` | `VerificationResult` with candidates, comparisons, decision, reasons |
| Image bytes + MIME | `extract_photo_fields(...)` | `PhotoResult` with four fields and a status; optionally passed to `verify_photo_result()` |
| Preserved OCR CSV rows | `reconcile_packaging(...)` | 11 consolidated rows with conflict/review flags |
| `Findings` (PROPOSED) | `GeminiClient.explain()` | `Explanation` with a reply and safe fallback flags |

## How does SMS identification work?

The message adapter normalises text, extracts a registration number when present (otherwise a name), and stores the original text as provenance. `src/candidate.py` retrieves by exact registration first; an unknown registration is never turned into a fuzzy name guess. Exact generic-name collisions retain every product. Fuzzy hits are suggestions only, with `requires_confirmation=True`.

## How does packaging-image extraction work?

Bytes are validated (JPEG/PNG/WebP, ≤5 MB), then sent to Gemini with a visible-text-only prompt, JSON response mode and a strict `PhotoFields` schema (`brand_name`, `registration_number`, `manufacturer`, `strength`; `extra="forbid"`). Missing text is `not visible`. Malformed responses and API errors become safe `error`/`rejected` statuses with no fabricated values. Package volume is **not** extracted by this schema. Results are observations and can be passed into `verify_photo_result()`.

## How does medicine verification work?

Candidates are compared field by field. `UNKNOWN` means not supplied; `MISMATCH` means a real contradiction; `CONFLICT` means two incompatible original values were preserved. Exact registration with corroboration and no conflicts yields `MATCH`. One exact brand hit without independent support yields `PARTIAL_MATCH`. Ambiguity, conflicts and unconfirmed suggestions route to manual review. No probability or confidence value is produced.

## The six decision statuses

`MATCH`, `PARTIAL_MATCH`, `MISMATCH`, `NO_MATCH`, `INSUFFICIENT_INFORMATION`, `MANUAL_REVIEW_REQUIRED`.

## What has been tested?

- **Offline:** 182 passing tests, 40 skipped live tests, 0 failed; deterministic probes of all six decisions; 22-image reconciliation in 2.04 ms with 0 diffs versus preserved results; all 11 packaging records (8 `NO_MATCH`, 3 review, zero `MATCH`).
- **Mocked:** Gemini explanation wording/safety, response schema, no-key behaviour, malformed responses, API-error classification.
- **Genuine live:** controlled explanation and structured-JSON operations earlier; Stage 5.3 recorded four successful image submissions across three bounded requests, all schema-valid. Live validation remains **PARTIAL**; the full live suite has **not** passed and was not run during packaging.

## What has not been validated?

Real-world OCR accuracy (ground truth is blank: 0/11 on every primary field), authoritative catalogue coverage, production-scale latency, and end-to-end backend behaviour. No accuracy percentage may be claimed.

## What does the backend team need to do?

1. Install `requirements.txt` and run `python -m pytest -q` in the release copy.
2. Supply `GEMINI_API_KEY` through your secure environment/secrets mechanism; optionally set `GEMINI_MODEL` (default `gemini-3.1-flash-lite`) and keep `AI_ML_MOCK=0` for live calls. Host env wins over `.env`; the key is loaded by the existing `GeminiClient`/`load_project_env()` implementation. Never embed or log the key.
3. Decide whether to accept the proposed `Findings` contract. Do not change `AWAITING_BACKEND_CONFIRMATION` until the owner approves.
4. Design an orchestration layer that keeps a human in the loop for every `MANUAL_REVIEW_REQUIRED`, fuzzy or generic-name result.
5. Preserve `UNKNOWN`, `MISMATCH` and `CONFLICT` distinctly in any UI or data store. Treat `similarity_score` as a retrieval hint, not confidence.
6. Treat OCR observations as untrusted input, never proof of authenticity.
7. Plan bounded, asynchronous calls for Gemini operations; one earlier expanded batch hit a 180-second limit.

## What decisions require backend-owner confirmation?

- Acceptance or rejection of `src/contracts.py` and its field semantics.
- Changing `AWAITING_BACKEND_CONFIRMATION` (currently `True`).
- Whether generic-name and fuzzy candidates may ever be auto-accepted (current engine never does).
- How manual review is presented and resolved.
- Whether any live OCR output may influence a regulatory decision (current design says no).
- Production go/no-go, which is **not** established by this handoff.

## Run it locally

```powershell
cd "release\Drug_SMS_Checker_AI_ML"
python -m pip install -r requirements.txt
python -m pytest -q
python tools\demo.py
python tools\interactive_server.py
```

Open `http://127.0.0.1:8765`; stop with `Ctrl+C`. Offline sections work with no key. Full details: `README.md`, `docs/BACKEND_INTEGRATION_GUIDE.md`, `docs/INTERACTIVE_TESTING_GUIDE.md`.
