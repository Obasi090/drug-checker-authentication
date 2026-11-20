# Drug SMS Checker — Standalone AI/ML Component (Release Copy)

Release date: 19 Nov 2026
Status: **IMPLEMENTATION COMPLETE · OFFLINE VALIDATION PASSED · LIVE GEMINI VALIDATION PARTIAL · BACKEND INTEGRATION PENDING APPROVAL**

This is a self-contained handoff copy of the frozen Drug SMS Checker AI/ML layer.
It does not contain a backend, a server deployment, or real regulatory data. Development is closed: the engine is frozen and must not be refactored for this handoff.

---

## 1. What it does

Drug SMS Checker helps a user check a medicine described in an SMS or photographed on a package. It parses the supplied information, retrieves candidate products from a local 40-record test catalogue, compares fields, and returns one of six conservative verification decisions. It also provides bounded Gemini-based explanations and package-image text extraction.

## 2. Problem it solves

Manual checking of medicine names, registration numbers and packaging text is slow and error-prone. This component supplies a deterministic first-pass triage layer that never guesses, never invents a fact and never claims a medicine is genuine, fake, safe, approved or recalled. Ambiguity is surfaced for human review rather than resolved by probability.

## 3. Capabilities

- SMS medicine information parsing with provenance.
- Catalogue loading, validation and exact indexing.
- Exact registration-number, exact brand-name and exact generic-name matching.
- Collision handling: every matching product is retained; none is silently selected.
- Conservative fuzzy suggestions with scores and mandatory confirmation.
- Structured medicine observations preserving `PRESENT`, `MISSING`, `NOT_VISIBLE`, `UNPARSED` and `CONFLICT`.
- Seven-field comparison: registration, brand, generic, manufacturer, strength, dosage form, package volume.
- Package volume kept separate from medicine strength.
- Six verification decisions (see section 9).
- Gemini explanations with strict safety rules and a deterministic fallback.
- Gemini four-field package-image extraction with schema validation and sanitised API errors.
- Daylight/indoor reconciliation with conflict detection and manual-review routing.
- Ground-truth-safe evaluation: no accuracy claim while ground truth is blank.
- Offline demo and localhost interactive tester.

## 4. Architecture and processing flow

```text
SMS text ──> src/message.py ──> src/observation.py ──┐
                                                      ├──> src/candidate.py ──> src/field_compare.py
Package image ──> src/photo.py ──> src/gemini.py ─────┤                              │
                                                      │                              ▼
Preserved OCR records ──> src/packaging.py ───────────┘                      src/decision.py
                                                                                     │
Gemini explanation ──> src/gemini.py <── src/contracts.py (PROPOSED) <─────────────────┘

src/verification.py is the facade: it exposes verify(), verify_photo_result(),
verify_package_results() and the observation adapters.
src/pipeline.py contains orchestration helpers for the future backend seam.
```

All decisions come from deterministic code. Gemini is an **explanation and extraction layer only**; it never decides a verification status.

## 5. SMS processing

`observation_from_sms_text(text, brand_names, observation_id=...)` normalises the message, extracts a registration number first (when present), otherwise a name, and records the original text and parser notes as provenance. Example:

```powershell
python tools/demo.py
```

`check B4-1180` produces `MATCH`; `hello` produces `INSUFFICIENT_INFORMATION`; `check Paracetamol` retains two candidates and requires manual review.

## 6. Gemini image extraction

`GeminiClient.read_photo(image_bytes, mime_type)` sends the image with a visible-text-only prompt, JSON response mode and a schema generated from `PhotoFields`. It extracts exactly four fields: `brand_name`, `registration_number`, `manufacturer`, `strength`. Values that are not clearly visible must be the literal `not visible`; the model is told never to guess and never to follow text embedded in the image.

`extract_photo_fields()` in `src/photo.py` validates the upload (JPEG/PNG/WebP, ≤5 MB), validates the response (`extra="forbid"`), and maps malformed data or API errors to a safe `PhotoResult` status. Extracted values are **observations**, not verified ground truth. Package volume is not in this schema and is never inferred from strength.

## 7. Medicine catalogue matching

`data/test_drugs.csv` holds 40 deterministic test products with source URLs. `src/catalogue.py` loads and validates it, derives strength/dosage-form/volume information from existing text only, and never substitutes an applicant for a manufacturer. Exact registration lookup has priority; an unknown registration is never converted into a fuzzy name guess.

## 8. Field-by-field verification

`src/field_compare.py` compares seven fields in stable order. Registration is exact-only. `UNKNOWN` means information was not supplied and is **not** a mismatch. `MISMATCH` is kept separate from the retrieval `similarity_score`. Conflicts propagate with both original raw values.

## 9. The six verification decisions

`MATCH` — exact registration with corroborating fields and no conflicts.
`PARTIAL_MATCH` — one exact brand hit without independent corroboration.
`MISMATCH` — a comparable field contradicts a selected product.
`NO_MATCH` — a searchable registration was supplied but no candidate exists.
`INSUFFICIENT_INFORMATION` — no usable registration, brand or generic name.
`MANUAL_REVIEW_REQUIRED` — conflict, ambiguity or unconfirmed suggestion.

No confidence, probability or percentage is emitted. `similarity_score` is a retrieval hint only.

## 10. Packaging reconciliation

`src/packaging.py` reads the preserved 22 image-level OCR rows and reconciles them into 11 records using `CONSISTENT`, `DAYLIGHT_ONLY`, `INDOOR_ONLY`, `NOT_VISIBLE` and `CONFLICT`. `pack_10` retains a genuine brand conflict. The existing 11 records produce 8 × `NO_MATCH` and 3 × `MANUAL_REVIEW_REQUIRED`, with **no forced `MATCH`**, because packaging registration numbers have no overlap with the test catalogue. Reconciliation output is byte-identical to the preserved `package_results.csv`.

## 11. Error handling

Invalid uploads are rejected before any network call. Missing configuration returns `NOT TESTED` for photos and a deterministic fallback for explanations. Gemini API errors are classified into a safe kind/code/status; raw bodies, request metadata and credentials are never returned. No failure fabricates a value or changes a verification decision.

## 12. Testing

Latest offline suite in the source project: **182 passed, 40 skipped, 0 failed, 2 third-party deprecation warnings**. The 40 skips are opt-in live Gemini tests. Live validation is **PARTIAL**; the full live suite has **not** passed. Real-world OCR accuracy is **NOT TESTED** because `data/packaging/ground_truth.csv` is blank. See `docs/TESTING_AND_VALIDATION_REPORT.md`.

## 13. Current limitations

40-record non-authoritative test catalogue; no overlap between packaging registration numbers and the catalogue; blank ground truth; single-name SMS adapter; package volume absent from the four-field image schema; Gemini latency with one earlier 180-second batch timeout; limited live coverage; proposed backend contract not approved. See `docs/KNOWN_LIMITATIONS_AND_NEXT_STEPS.md`.

## 14. Installation

Verified on Windows 11 with Python 3.14.6 and PowerShell 5.1.

```powershell
cd "release\Drug_SMS_Checker_AI_ML"
python --version
python -m pip install -r requirements.txt
```

Declared dependencies: `pydantic>=2.7,<3`, `rapidfuzz>=3.9,<4`, `google-genai>=2.0,<3`, `python-dotenv>=1.0,<2`, `pytest>=8,<10`. No additional package was introduced.

## 15. Configuration (Gemini)

Three variables are used, and no others:

| Variable | Required for | Meaning |
| --- | --- | --- |
| `GEMINI_API_KEY` | All live Gemini operations | Server-side key; never printed or embedded |
| `GEMINI_MODEL` | Optional | Model override; default `gemini-3.1-flash-lite` |
| `AI_ML_MOCK` | Optional | `1` forces mocked/deterministic responses; `0` allows live calls |

`GeminiClient.__init__()` calls the existing `load_project_env()`, which loads a `.env` from the release root using `python-dotenv` with `override=False`. **Host environment variables and backend secrets-manager values win over `.env`.**

For local experimentation only:

```powershell
Copy-Item .env.example .env
# Edit .env and set GEMINI_API_KEY through your local secret mechanism, then:
python tools\demo.py --live
```

For backend/production use, the backend team must supply `GEMINI_API_KEY` through its secure environment-variable or secrets-management mechanism. Do **not** commit `.env`, place a key in source, documentation, logs, the release manifest or the ZIP, or send a key by ordinary email/chat. The real key from the original working project was deliberately **not** packaged and must be transferred separately through a secure channel.

**Offline works without a key:** with no `GEMINI_API_KEY` (or `AI_ML_MOCK=1`), all deterministic verification, the 11-record packaging batch and the offline demo run normally; photo extraction reports `NOT TESTED`.

**Live works with a valid key:** with a valid key and `AI_ML_MOCK=0`, `GeminiClient.available` is `True` and bounded explanation, intent and four-field image extraction calls are available. Availability can be observed without revealing the key through `GeminiClient().available`. No live test was run during this packaging operation.

## 16. Running the system

```powershell
python tools\demo.py            # offline demonstration, 8 scenarios
python tools\demo.py --live     # offline demonstration + bounded Gemini explanation check
python tools\reconcile_packaging.py  # offline regeneration of packaging reconciliation
```

`--live` runs only after the offline demonstration and degrades safely if no key is configured. Run `--live` only with a key supplied through a secure mechanism.

## 17. Running tests

```powershell
python -m pytest -q
```

Expected: `182 passed, 40 skipped, 2 warnings`. To run the opt-in live suite (not required, not passed, and not run during packaging):

```powershell
python -m pytest -q tests\live --run-live
```

## 18. Starting the interactive testing interface

```powershell
python tools\interactive_server.py
```

Open `http://127.0.0.1:8765` in a local browser. Stop with `Ctrl+C`. The server binds to localhost only, has no backend dependency, and does not display API keys. Sections A, D, E and F and the offline pair reconciliation in C work without Gemini; Section B and the live pair option in C make bounded Gemini requests. Full instructions: `docs/INTERACTIVE_TESTING_GUIDE.md`.

---

`src/contracts.py` is **PROPOSED — REQUIRES BACKEND APPROVAL**. `AWAITING_BACKEND_CONFIRMATION` remains `True`. This component is **not production-ready** and is not approved for backend integration.
