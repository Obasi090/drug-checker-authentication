# Local Interactive Testing Guide - Drug SMS Checker AI/ML

Date: 19 Nov 2026
Status: test harness only. The frozen verification engine was **not** modified.

## 1. Approach and dependencies

A small local web interface was chosen because it can be implemented with the
Python standard library (`http.server`, `json`, `base64`, `urllib.parse`) plus the
dependencies already declared in `requirements.txt` (`pydantic`, `rapidfuzz`,
`google-genai`, `python-dotenv`). **No new dependency was installed and no package
file was changed.** There is no backend, no database, no account and no cloud
hosting. The server binds to `127.0.0.1` only, so it cannot be reached from another
machine.

Files added for this environment:

- `tools/interactive_server.py` - localhost HTTP server and API endpoints
- `tools/interactive_ui.html` - single-page interface (inline CSS/JS, no framework)

Safety properties:

- The API key is read only by the existing `GeminiClient` `.env` loader; it is
  never displayed, logged, or returned by any endpoint.
- Uploaded bytes stay in memory for the duration of the request only.
- Offline sections (A, D, E, F and the offline pair reconciliation in C) work with
  no key and no network.
- Section B and the "Extract both and reconcile" button in C make live Gemini
  requests and show a visible loading indicator.
- No result is ever labelled verified, genuine, approved or safe.

## 2. Start and stop - exact PowerShell commands

Open PowerShell in the project root:

```powershell
cd "C:\Users\DELL\Documents\Default Project"
```

One-time dependency check (skip if already installed):

```powershell
python -m pip install -r requirements.txt
```

Start the tester:

```powershell
python tools/interactive_server.py
```

Then open this address in your browser:

```text
http://127.0.0.1:8765
```

Expected terminal output:

```text
Drug SMS Checker local tester: http://127.0.0.1:8765
Gemini availability is shown in the page header; no API key is displayed.
Offline sections remain usable when Gemini is unavailable. Press Ctrl+C to stop.
```

Stop it by pressing `Ctrl+C` in that terminal. If the terminal is no longer
available, stop the listener by PID:

```powershell
Get-NetTCPConnection -LocalPort 8765 -State Listen |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

If the port is already in use, either stop the existing process as above or change
`PORT = 8765` in `tools/interactive_server.py` and use the new address. No core
engine file is involved.

## 3. Using the interface

The header always shows Gemini availability, model name, catalogue row count, and
the reminder that the key is never displayed.

### A. SMS Medicine Checker

1. Type a message, for example `Please verify this medicine: Acimox Capsule` or
   `check B4-1180`.
2. Click **Check message**.
3. The result card shows the original SMS, parsed information (including whether
   the registration number was extracted), every observed field with its state,
   catalogue candidates with `similarity_score`, field comparisons with `UNKNOWN`
   kept distinct from `MISMATCH`, the final decision, reasons, notes and the
   manual-review flag.

No network call is made. Example: `check B4-1180` → `MATCH`, one candidate,
generic/manufacturer/dosage form remain missing.

### B. Medicine Image Checker

1. Choose a local `.jpeg`, `.jpg`, `.png` or `.webp` image (max 5 MB). A preview is
   shown. A bundled example is
   `data\packaging\daylight\pack_01.jpeg`.
2. Click **Extract and verify**. A "Calling Gemini..." indicator appears.
3. The card shows the schema result, elapsed time, brand, registration,
   manufacturer, strength, and **package volume separately as `not visible`**
   with the note that the existing four-field schema does not extract it.
4. If extraction succeeds, the engine's candidates and decision are shown using
   that observation. If it fails, the error is visible and no verification is
   invented.

One bounded live request is made. Key availability, not the key itself, is shown.
Extracted values are observations, never verified ground truth.

### C. Daylight and Indoor Comparison

Two options:

- **Live pair:** select a daylight and an indoor image of the same medicine, then
  click **Extract both and reconcile**. Two bounded requests are made. The result
  lists each field with `CONSISTENT`, `DAYLIGHT_ONLY`, `INDOOR_ONLY`,
  `NOT_VISIBLE` or `CONFLICT`, the two raw values, the chosen value, the manual
  review flag and elapsed time.
- **Offline pair:** choose a medicine id from the dropdown and click **Reconcile
  existing pair offline**. This uses the preserved `ocr_results.csv` records and
  makes no network call.

The bundled pair `data\packaging\daylight\pack_01.jpeg` and
`data\packaging\indoor\pack_01..jpeg` (note the double dot in the preserved
filename) produces all-consistent / not-visible fields and manual review `NO`.

### D. Catalogue Search

Enter any part of a brand name, generic name, registration number, applicant or
manufacturer and click **Search**. Up to 50 matches are shown with brand, generic,
registration, applicant, manufacturer, strength and dosage form. Blank values stay
blank; nothing is filled in. Example: `Paracetamol` returns 3 records.

### E. Verification Engine Tester

Click **Run evidence tour**. Seven real engine results are rendered with full
evidence: MATCH, PARTIAL_MATCH, MISMATCH, NO_MATCH, INSUFFICIENT_INFORMATION,
MANUAL_REVIEW_REQUIRED (conflict), and the **Paracetamol generic-name collision**
showing two retained candidates and no selected product.

### F. Existing Packaging Dataset

Click **Run all 11 records**. The table shows every medicine id, decision,
candidates, manual-review flag and reasons. Expected summary: **11 records**,
**Any forced MATCH: False**, **pack_10 manual review: True**, and
8 × `NO_MATCH` + 3 × `MANUAL_REVIEW_REQUIRED`. This is the expected safe outcome
because packaging registration numbers do not overlap the 40-record catalogue.

## 4. Verified smoke-test results

During construction, every HTTP endpoint was called directly and all returned
200 with real data:

| Endpoint | Result |
| --- | --- |
| `/` | HTML UI served, 17,640 bytes |
| `/api/config` | Gemini available, model `gemini-3.1-flash-lite`, 40 catalogue rows |
| `/api/sms` | `PARTIAL_MATCH` for the Acimox example |
| `/api/catalogue?q=Paracetamol` | 3 matches |
| `/api/decisions` | 7 cases with the expected statuses |
| `/api/packages` | 11 records, no forced `MATCH`, `pack_10` review true |
| `/api/compare_dataset` | reconciliation result, manual review false for `pack_01` |

Live UI checks: `/api/photo` returned `ok`, schema `VALID (PhotoFields, extra=forbid)`
in 5,040.5 ms and engine `NO_MATCH`; `/api/compare` completed two image
submissions in 4,172.1 ms with all fields consistent. Browser inspection confirmed
the rendered SMS result card and no console errors. Only a small controlled sample
was used; no rate-limit stress test was performed.

## 5. Troubleshooting

| Problem | Action |
| --- | --- |
| Port 8765 in use | Stop the listener with the PowerShell command in section 2, or change `PORT` |
| Gemini unavailable in header | Expected offline mode; sections A, D, E, F and offline C still work |
| Live extraction fails | The error is shown and no verification is invented; check connectivity/quota, then retry once |
| Image rejected | Use JPEG/PNG/WebP under 5 MB |
| Page looks stale | Refresh the browser; caching is disabled by the server |
| Need to confirm no listener remains | `Get-NetTCPConnection -LocalPort 8765 -State Listen` |

## 6. What this environment is not

It is a local, single-user testing tool. It is not a backend service, not a
production UI, not a mobile interface, and not an accuracy benchmark. It does not
change decision logic, does not write to any protected data file, and does not
alter `AWAITING_BACKEND_CONFIRMATION`.
