# AI/ML prerequisite recovery check

Prepared 19 Nov 2026. Only items verified in this session are listed as obtained.

## 1. Resources obtained (verified)

| Resource | Status | Evidence |
| --- | --- | --- |
| Workspace versions | Verified | Node `v24.18.0`, npm `11.16.0`, Python `3.14.6`, opencode `1.19.6`. Playwright MCP needs Node ≥20 — satisfied. |
| Project PDFs | Obtained | `docs/Drug SMS Checker Problem Statement and Solution.pdf`, `docs/Drug SMS Checker Team Guide by Role.pdf` (copied byte-for-byte from `C:\Users\DELL\Documents\competition`). The two DOCX guides were read from the same folder. |
| NAFDAC Greenbook visible fields | Observed with Playwright | Product Name, Active Ingredients, Product Category, NRN, Form, ROA, Strengths, Applicant Name, Approval Date, Status. Detail pages also show Manufacturer Name, Manufacturer Country, ATC code, Marketing Category, Packsize, SMPC link, Expiry Date. |
| Drug catalogue sample | Obtained | `data/test_drugs.csv` — 40 real products filtered to category **Drugs** in the Greenbook search table, each with a source URL. |
| Registration-number formats actually observed | Obvious from sample, not invented | `04-0858`, `A11-0236`, `A4-101970`, `B4-1180`, `C4-1202`, `A6-0592`. Parser uses `[A-Z0-9]{2,3}-[0-9]{4,6}`; dates such as `2021-08-03` do not match. |
| Manufacturer values | Partially obtained, explicitly only | Five detail pages were opened; only those five rows in the CSV have a manufacturer. Applicant Name was **not** treated as manufacturer. Example: `1980 Azithromycin USP 250 mg Tablets` — applicant `1980 Pharmaceutical Limited`, manufacturer `Surmount Laboratories Pvt Ltd` (INDIA). |
| Applicant ≠ manufacturer | Confirmed | Same example, plus `Actifed Cold Tablets`: applicant `GlaxoSmithKline Consumer Nigeria PLC (GSK)`, manufacturer `GlaxoSmithKline S.A.E` (EGYPT). |
| MCP servers | Connected | `rea`, `firecrawl`, `playwright` appeared in `opencode mcp list`; Playwright was used successfully. |
| Dependencies | Installed | `pydantic 2.13.4`, `rapidfuzz 3.14.6`, `google-genai 2.17.0`, `pytest 9.2.0`, `python-dotenv 1.x`. `google-genai` config API was introspected before coding (`GenerateContentConfig(system_instruction=..., response_schema=...)` is accepted). |
| Environment convention | Prepared | `.env.example` with `GEMINI_API_KEY`, `GEMINI_MODEL`, `AI_ML_MOCK`; `.gitignore` excludes `.env`. `GeminiClient` loads the project `.env` with `python-dotenv` (`override=False`, so host env wins). |
| Live model | Verified | Default is now `gemini-3.1-flash-lite`. `gemini-2.5-flash` returns 404 "no longer available to new users"; `gemini-3.8-flash` (the model named in that 404) returned 503 high-demand at test time. Override with `GEMINI_MODEL`. |
| Live API | Verified, then blocked | With `gemini-3.1-flash-lite`: real `generate_content`, model lookup, structured JSON and image-part input all passed (`4 passed`). The image probe is a 1×1 PNG, **not** medicine-pack OCR. The upstream API later hung mid-suite, so the full live evaluation is incomplete; see `docs/AI_ML_LIVE_TEST_REPORT.md`. |

### Sources

- Greenbook home / search: https://greenbook.nafdac.gov.ng/ (category `Drugs`, 100 rows displayed in one targeted view)
- Example detail pages: https://greenbook.nafdac.gov.ng/products/details/8875, `/12545`, `/12546`, `/6756`, `/6678`
- Supplied project documents (see `docs/` and the `competition` folder) — Team Guide §2.4 (proposed findings format), §4 (AI/ML tasks), §6; AI/ML Technical Documentation §§3–4, 9–11.

## 2. Missing or unavailable resources (do not claim otherwise)

1. **Existing Drug SMS Checker repository / backend.** None was present. The opened workspace contained an unrelated PHP calculator site; those files were moved to `C:\Users\DELL\Documents\PHP_Calculator_Backup_2026-11-19`. No Python engine, API, data model or tests were found to inspect. This is why `src/contracts.py` is marked **PROPOSED / AWAITING BACKEND CONFIRMATION**.
2. **Confirmed findings contract.** Only the Team Guide proposal exists. No backend owner confirmation was available.
3. **Firecrawl.** Configured but unusable in this session: `getaddrinfo ENOTFOUND mcp.firecrawl.dev` on both scrape and search. No Firecrawl result is claimed. All web facts above came from Playwright.
4. **GEMINI_API_KEY.** Present in the project `.env` (value never printed or committed); absent from the shell environment. `GeminiClient` now loads `.env` server-side via `python-dotenv`. Deterministic tests still mock; live calls run only through the opt-in `--run-live` suite.
5. **Real medicine packaging photographs.** 11 real packs × 2 lighting conditions are now present under `data/packaging/` (22 images). No independently verified ground truth is populated, so no accuracy measurement was performed. **Photo OCR accuracy: NOT TESTED.** The 11-pack × 2-lighting template at `tests/photo_test_template.csv` has all 22 results `pending`.
6. **Official NAFDAC alert notices / MAS short-code instructions.** Not supplied or verified. No alert records were created; test alerts are synthetic and labelled as such.
7. **Backend/web integration endpoint.** Not available; `ProposedBackendAdapter` is only a seam.

## 3. Required teammate handoffs

- **Backend owner:** confirm or correct the field names/types in `src/contracts.py`, then supply a callable `check(query, query_type) -> dict` (or the real endpoint) so `ProposedBackendAdapter` can be replaced without touching AI modules. Confirm the real registration formats and the `matched_by` values used for name-only alerts.
- **Presenter / data owner:** use the 11 real pack pairs already captured; independently verify `ground_truth.csv` from the physical packs; supply verified NAFDAC notice URLs for any alerts; confirm MAS scratch-code instructions.
- **Web developer:** call `pipeline.prepare_lookup` → show confirmation UI → call backend → call `pipeline.explain`; show raw findings next to the reply. Never send `GEMINI_API_KEY` to the browser.
- **Whoever provisions secrets:** set `GEMINI_API_KEY` in the server environment only; optional `GEMINI_MODEL`; keep `AI_ML_MOCK=1` for deterministic demo fallback.

## 4. Exact next actions

1. Get the backend owner to confirm `Findings` (or paste the real payload) and wire the real lookup into `ProposedBackendAdapter`.
2. Keep `GEMINI_API_KEY` server-side only (it is already in the local `.env`), leave `AI_ML_MOCK` unset, and run the opt-in live suite: `python -m pytest -q tests/live --run-live`. Record results in `docs/AI_ML_LIVE_TEST_REPORT.md`; transient 503s are reported, not hidden by mocks.
3. Use the 11 real pack pairs already captured. Independently verify `ground_truth.csv` from the physical packs, review `pack_10`'s brand conflict, then fill `tests/photo_test_template.csv` and compute exact reg-number accuracy only when verified ground truth exists. If below ~70%, exclude live OCR from the demo.
4. Research official NAFDAC notices only with a verified source link before any alert enters real data; never import LLM-proposed fields without human review.
5. Run `python -m pytest -q` after every integration change; keep zero silent wrong medicine selections.
