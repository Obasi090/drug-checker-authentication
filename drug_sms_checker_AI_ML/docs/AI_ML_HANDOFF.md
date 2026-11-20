# AI/ML handoff — 19 Nov 2026

## Status summary

- AI layer implemented against a **proposed** findings contract; no backend repository or API was found. Contract is explicitly awaiting backend confirmation (`AWAITING_BACKEND_CONFIRMATION = True`).
- **Live Gemini is activated** (key loaded server-side from `.env` via `python-dotenv`). Default model is now `gemini-3.1-flash-lite`; `gemini-2.5-flash` returned 404 "no longer available to new users". The opt-in live suite is separate from the deterministic offline suite. Full live evaluation was blocked by upstream API hangs; 4/4 probes and 17 consecutive explanation cases passed, with no failures observed. Exact status: `docs/AI_ML_LIVE_TEST_REPORT.md`.
- **Photo OCR accuracy: NOT TESTED** — 11 real pack pairs now exist under `data/packaging/`, but `ground_truth.csv` verification fields are empty. Only a non-pack image-input capability probe was run. Live OCR must be excluded from the demo until independently verified ground truth is supplied.
- Offline tests: **141 passed, 40 live tests skipped by default** (`python -m pytest -q`). Two third-party warnings (`anyio` pytest-10 rename and `google-genai` union-type deprecation); no test failure.

## Changed / added files

| Path | Purpose |
| --- | --- |
| `src/contracts.py` | Proposed typed findings contract, validator, `BackendLookup` protocol, `ProposedBackendAdapter` seam. |
| `src/message.py` | Normalisation, exact-span NRN extraction, safe filler removal, deterministic intent. |
| `src/fuzzy.py` | RapidFuzz ranking over brand/generic aliases, token gate, exact-first, confirmation gate. |
| `src/gemini.py` | Server-side system instruction, mock explainer, output validation/fallback, exact-span NLU, bounded vision interface. Loads project `.env` (`python-dotenv`, `override=False`); default model `gemini-3.1-flash-lite`. Sanitises Pydantic schemas to remove `additionalProperties`, catches `APIError` for explain/extract/photo paths, classifies photo errors into safe kinds and disables thinking (`thinking_budget=0`). Uses `google.genai.Client` / `GenerateContentConfig` verified against installed 2.17.0. |
| `src/photo.py` | Four-field photo extraction interface, upload validation, no retention, NOT TESTED status, canonical missing-value helper and sanitised `PhotoReadError`. |
| `src/packaging.py` | Deterministic 11-pack reconciliation, conflict classification, package-volume separation and ground-truth safety evaluation. |
| `src/pipeline.py` | `prepare_lookup` / `explain` integration helpers. |
| `src/__init__.py` | Package marker. |
| `data/test_drugs.csv` | 40 Greenbook products with source URLs; manufacturer only on 5 explicitly verified rows. |
| `data/packaging/ocr_results.original.csv` | Backup of the original image-level OCR records before filename correction. |
| `data/packaging/package_results.pre_reconciliation.csv` | Backup of the previous consolidated dataset before regeneration. |
| `docs/PACKAGING_DATASET_VALIDATION.md` | Evidence for the 11-pack decision, actual filename mapping and integrity checks. |
| `docs/PHOTO_COMPARISON_REPORT.md` | Multi-image comparison, one-sided fields, genuine conflicts and manual review. |
| `docs/GROUND_TRUTH_STATUS.md` | Empty ground-truth status and safe evaluation workflow. |
| `docs/AI_ML_PREREQUISITES.md` | Recovery check, sources, missing resources, handoffs, next actions. |
| `docs/*.pdf` | Two supplied project PDFs, copied unchanged. |
| `tests/` | 45 message cases, 32 misspellings + 2 safety cases, 29 explanation cases, 4 photo/harness cases, 15 packaging cases, 3 ground-truth cases, 7 photo-API-error cases, 4 integration/contract cases; plus 40 opt-in live cases. |
| `tests/photo_test_template.csv` | 11 packs × 2 lighting conditions (22 captures); all results `pending`. |
| `tests/live/test_live_gemini.py` | Opt-in live evaluation: 36 synthetic explanation cases + 4 Phase 1 probes. Safety categories run twice. Never counted as offline tests. |
| `tools/reconcile_packaging.py` | Offline regeneration of `package_results.csv` from `ocr_results.csv`. |
| `tools/photo_eval.py` | Read-only 11-pack × 2-lighting workflow; prints `REAL-PACK OCR ACCURACY: NOT TESTED` until independently verified ground truth is filled. |
| `requirements.txt`, `.env.example`, `.gitignore`, `README.md` | Install/env/safety documentation; `python-dotenv` added. |

The PHP calculator files originally in this folder were **moved** (not deleted) to `C:\Users\DELL\Documents\PHP_Calculator_Backup_2026-11-19`.

## Install / env / test

```powershell
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Set GEMINI_API_KEY in .env (server-side only); AI_ML_MOCK=1 forces mocks
python -m pytest -q                        # offline, deterministic, no network
python -m pytest -q tests/live --run-live  # opt-in live Gemini evaluation
python tools/photo_eval.py                 # real-pack OCR workflow (read-only)
```

## Interfaces

```python
from src.pipeline import prepare_lookup, explain
from src.fuzzy import DrugCatalogue
from src.gemini import GeminiClient
from src.contracts import ProposedBackendAdapter

catalogue = DrugCatalogue.from_csv("data/test_drugs.csv")
prepared = prepare_lookup("abeg check ZZ-1234", catalogue)   # stage, await_confirmation, lookup_query/type
findings = ProposedBackendAdapter(backend_check).check(prepared.lookup_query, prepared.lookup_type)
reply = explain("check ZZ-1234", findings, GeminiClient())
```

`MessageIntent`, `Suggestion`, `Findings`, `Explanation`, `PhotoFields` are Pydantic models. No regulatory decision is exposed by any AI module.

## Test counts and actual results

| Suite | Cases | Result |
| --- | --- | --- |
| Message extraction (`test_message.py`) | 45 messy messages | 45/45 pass; exact span preserved; no silent name inference from symptoms. |
| Spelling (`test_fuzzy.py`) | 32 misspellings + 2 safety assertions | 32/32 correct candidate or safe clarification. **Zero silent wrong selections** — every fuzzy result requires confirmation. |
| Explanation (`test_gemini.py`) | 25 mock cases (5 normal, 5 alert, 5 not-found, 5 safety traps run twice, 5 messy/Pidgin) + 1 no-key check + 1 schema regression + 2 refusal-guard regressions | 29/29 pass. Safety traps passed twice consecutively. |
| Photo (`test_photo.py`) | 4 harness/validation cases | 4/4 pass. Accuracy **NOT TESTED**. |
| Packaging (`test_packaging.py`) | 15 dataset/reconciliation cases | 15/15 pass; 11 packs, 22 images, conflict rules verified. |
| Ground truth (`test_ground_truth.py`) | 3 safety cases | 3/3 pass; empty ground truth yields no accuracy claim. |
| Photo API errors (`test_photo_api_errors.py`) | 7 cases | 7/7 pass; errors are classified and sanitised. |
| Integration/contract (`test_integration.py`) | 4 cases | 4/4 pass. |
| **Offline total** | **141** | **141 passed, 40 live skipped, 2 third-party warnings**. |
| Live Gemini (`tests/live`, opt-in) | 36 synthetic cases (+13 safety reruns) + 4 probes | See `docs/AI_ML_LIVE_TEST_REPORT.md`; never counted as offline. |

## Known failures / limitations

- Live Gemini availability is volatile: `gemini-2.5-flash` is retired (404), `gemini-3.8-flash` returned 503 high-demand, and `gemini-3.1-flash-lite` later stopped responding mid-run, so the full 40-item live suite did not complete. The harness paces requests and retries only transient 429/5xx; persistent errors are reported as failures, never replaced by mocks. See `docs/AI_ML_LIVE_TEST_REPORT.md`.
- Real-pack OCR accuracy remains **NOT TESTED** because `ground_truth.csv` is empty. `pack_10` has one genuine brand-name conflict requiring human review; all other manual-review flags were recalculated to `false`.
- Firecrawl MCP DNS failure (`ENOTFOUND mcp.firecrawl.dev`); not used for any claim in the docs.
- Only the first 100 Greenbook drug rows were inspected (one targeted view), not the whole catalogue.
- Manufacturer field present on only 5 CSV rows; blank means "not explicitly verified", never guessed.
- Proposed contract may not match the eventual backend; `adapt_findings` will reject an incompatible payload rather than invent fields.

## What other teams must do

1. **Backend:** confirm `Findings` field names/types and provide the lookup callable/endpoint; confirm `matched_by` vocabulary and real NRN formats.
2. **Web:** gate every fuzzy correction behind a confirmation UI; render raw findings beside the AI reply; never expose the key.
3. **Presenter/data:** independently verify `ground_truth.csv` from the 11 real packs already captured; review the `pack_10` brand conflict; supply verified alert notices and MAS instructions.

## Demo / fallback recommendation

- Demo the safe path: messy misspelling → candidate + confirmation → reg-number lookup → findings card → live explanation (fallback to the deterministic mock if the API errors).
- Show a safety trap (dose / "is it genuine") and the redirect; the same guard rejects unsafe live output.
- **Do not demonstrate live photo OCR** until real-pack accuracy is measured. Show the 11-pack template and label it NOT TESTED.
- If Gemini is unavailable, use the built-in mock; the findings card remains visible so the demo is still honest.
