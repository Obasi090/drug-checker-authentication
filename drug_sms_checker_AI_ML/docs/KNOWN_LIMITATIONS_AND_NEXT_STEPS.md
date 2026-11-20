# KNOWN LIMITATIONS AND NEXT STEPS — Drug SMS Checker AI/ML

Date: 19 Nov 2026
Status: development closed; this document records limitations that must be carried into any backend discussion.

## 1. Catalogue limitations

`data/test_drugs.csv` contains **40 deterministic test records** with source URLs. It is not a complete or authoritative regulatory register. Absence from it means "not found in the supplied test catalogue", not "not registered". No live Greenbook feed or refresh mechanism exists.

**After the competition:** source an authoritative, versioned catalogue with an owner, update cadence, provenance and a documented coverage statement. Keep the current SHA-256 metadata pattern for reproducibility.

## 2. No confirmed packaging/catalogue overlap

The three registration numbers observed across the 11 packaging records have **zero overlap** with the 40-record test catalogue. Consequently the correct packaging outcomes are `NO_MATCH` or `MANUAL_REVIEW_REQUIRED`; no package is forced to `MATCH`. This is a data limitation, not a defect.

**After the competition:** obtain overlapping samples whose identities are independently verified, then re-run the batch to exercise positive matches end-to-end.

## 3. Blank ground truth

`data/packaging/ground_truth.csv` has 0/11 populated values for all four primary fields. `evaluate_ground_truth()` skips every field and returns `NOT TESTED`, `accuracy_tested=False`, 0 scored and 44 skipped fields.

**After the competition:** have a qualified reviewer transcribe values from the physical packages into ground truth independently of Gemini and OCR. Never fill it from `ocr_results.csv`, `package_results.csv`, engine output or online assumptions.

## 4. No independently measured OCR accuracy

Because ground truth is empty, no OCR accuracy, precision, recall or success percentage can be calculated. Stage 5.3 recorded four successful schema-valid image submissions across three bounded requests; this proves the extraction *mechanism*, not correctness.

**After the competition:** run a pre-registered evaluation against populated ground truth, report per-field results with confidence intervals, and only then discuss accuracy.

## 5. Gemini latency and timeout history

The SDK uses a 15,000 ms timeout and at most two attempts. Local observations: 7.6 s single extraction, 5.0 s UI image path, 4.2 s two-image pair. One earlier expanded live batch stopped at the **180-second limit**.

**After the competition:** make all Gemini work asynchronous in the backend, apply per-request and end-to-end deadlines, consider batching strategies, and add idempotent retries with backoff. Never block SMS verification on a Gemini call.

## 6. Limited live test coverage

Live validation is **PARTIAL**. Controlled explanation, structured-JSON and real-image operations succeeded earlier, and Stage 5.3 added four image submissions, but the full 40-test live suite has **not** passed and must not be described as passed.

**After the competition:** run the opt-in suite deliberately with a valid key, record exact outcomes, and keep synthetic/safe fixtures so no real medicine is labelled by a demo.

## 7. Package volume not in the extraction schema

`PhotoFields` contains exactly four fields: `brand_name`, `registration_number`, `manufacturer`, `strength`. Package volume is a separate observation field in the engine but is **not** extracted from images; it must be displayed as "not extracted", never inferred from strength. The preserved OCR records do contain volume values for reconciliation.

**After the competition:** extend the extraction schema deliberately (with tests and a new ground-truth column) if volume verification is required. Do not retrofit it into the frozen implementation.

## 8. Backend contract unapproved

`src/contracts.py` is marked **PROPOSED** and `AWAITING_BACKEND_CONFIRMATION = True`. It was not modified. `Mismatch` fields are explicitly provisional, and `ProposedBackendAdapter` is an example only. No HTTP endpoint or production API exists.

**After the competition:** obtain backend-owner sign-off on field semantics, confirmation rules, human-review workflow and status mapping before changing the flag or writing adapters.

## 9. Single-name SMS adapter

The SMS adapter has one `name` slot. A generic name typed into the SMS text is stored in `brand_name`, so comparisons may show `brand_name = MISMATCH` even though retrieval correctly used the text as a name. The decision remains conservative — retain candidates, ask a human — but the explanation can look confusing.

**After the competition:** agree with the backend on an explicit brand/generic discriminator or accept the review behaviour and document it in the user interface.

## 10. Production readiness not established

There is no deployment, monitoring, auth, rate-limit strategy, audit trail, backup, or authoritative data source in this component. No real-world accuracy claim, no backend integration test and no production go/no-go decision exists.

**After the competition:** treat this as a research/competition prototype. Establish an ownership model, secure key management (backend secrets manager), observability, a review workflow and a formal acceptance test before any production use.

## Status summary

- IMPLEMENTATION COMPLETE — yes, for the standalone AI/ML layer.
- OFFLINE VALIDATION PASSED — 182 passed, 40 skipped, 0 failed.
- LIVE GEMINI VALIDATION PARTIAL — bounded successes only.
- REAL-WORLD OCR ACCURACY NOT TESTED — ground truth blank.
- BACKEND INTEGRATION PENDING APPROVAL — contract proposed, flag unchanged.
- PRODUCTION READINESS — not established; do not claim it.
