# Competition Demonstration Guide - Drug SMS Checker AI/ML

Date: 19 Nov 2026
Component status: **FROZEN** - the demo reads the existing engine; it does not change it.
Demo scripts: `tools/demo.py` (offline-first) and this guide.

---

## 1. Purpose

This guide gives a reproducible, terminal-only demonstration of the existing
standalone verification engine. Every decision shown is produced by the frozen
code against the local 40-row test catalogue and the preserved packaging OCR
records. Nothing in the demonstration is a hand-written "successful" result.

---

## 2. Installation prerequisites

Verified workspace versions: Windows 11, Python `3.14.6`, PowerShell 5.1.

1. Open PowerShell in the project root:

   ```powershell
   cd "C:\Users\DELL\Documents\Default Project"
   ```

2. Install the declared dependencies (only needed once):

   ```powershell
   python -m pip install -r requirements.txt
   ```

   Required packages: `pydantic`, `rapidfuzz`, `pytest`. `google-genai` and
   `python-dotenv` are only needed for the optional live demonstration.

3. Confirm the environment (optional sanity check):

   ```powershell
   python --version
   python -m pytest -q
   ```

   Expected test result: `182 passed, 40 skipped, 2 warnings in ~4 s`.
   The 40 skips are opt-in live Gemini tests.

No internet connection, API key, backend, or `.env` file is needed for the
default demonstration. The script reads only:

- `data/test_drugs.csv`
- `data/packaging/package_results.csv`

and imports only existing `src/` modules. It writes no files.

---

## 3. Running the offline demonstration

From the project root:

```powershell
python tools/demo.py
```

Optional: save the transcript for the judges:

```powershell
python tools/demo.py | Tee-Object -FilePath "$env:TEMP\drug-sms-demo.txt"
```

Optional: show help / argument handling:

```powershell
python tools/demo.py --help
```

The script configures stdout as UTF-8 with safe replacement, so the catalogue's
non-ASCII text (for example `alpha-beta Arteether`) will not crash a Windows
console code page. Plain ASCII separators are used for readability.

---

## 4. Running the optional Gemini demonstration

The live section is **separate and opt-in**. It runs only after the complete
offline demonstration and can never prevent it.

```powershell
python tools/demo.py --live
```

What it does:

- loads the existing `.env` through the existing `src.gemini.GeminiClient`
  (`python-dotenv`, host environment wins, key never printed);
- prints only the configured model name and `Gemini available: True/False`;
- sends **one** bounded `explain()` request using a **synthetic** record labelled
  `SYNTHETIC TEST RECORD` (fictional product `DEMO Product Alpha`, fictional
  registration `ZZ-1234`, `example.invalid`-style source metadata is not used);
- uses the SDK's 15-second timeout with at most two SDK attempts;
- reports the reply, then states explicitly that this is not verification and
  not backend integration approval.

Rehearsing the skip path without making a network call:

```powershell
$env:AI_ML_MOCK = '1'
python tools/demo.py --live
Remove-Item Env:\AI_ML_MOCK
```

Expected skip output when no key is available or mock mode is enabled:

```text
  Gemini available: False (API key is never printed)
  Skipped: no usable GEMINI_API_KEY, or mock mode is enabled.
  The offline demonstration above is unaffected.
```

Any exception in the live section is caught, reported by exception type only
(never by raw message, which could contain request metadata), and the script
still exits successfully. No API key value is ever printed.

---

## 5. Expected outputs

The header prints the catalogue path, its SHA-256, all six decision statuses,
and the safety disclaimer. Then eight scenarios appear.

| # | Scenario | Original input | Expected final status | Key evidence shown |
| --- | --- | --- | --- | --- |
| 1 | MATCH | `check B4-1180` | `MATCH` | Exact registration selects `1980 Azithromycin USP 250 mg Tablets [B4-1180]`; other fields are `UNKNOWN`, not conflicts |
| 2 | PARTIAL_MATCH | `check Acimox Capsule` | `PARTIAL_MATCH` | Exact brand candidate `Acimox Capsule [A4-8982]`; no independent corroborating field; registration remains unknown |
| 3 | MISMATCH | constructed: registration `B4-1180`, generic `Gabapentin` | `MISMATCH` | Registration priority selects the azithromycin record; generic field is `MISMATCH`; the Gabapentin candidate is retained but not selected |
| 4 | NO_MATCH | `check ZZ-9999` | `NO_MATCH` | Searchable registration supplied, no candidate found; fuzzy suggestions suppressed for an unknown registration number |
| 5 | INSUFFICIENT_INFORMATION | `hello` | `INSUFFICIENT_INFORMATION` | No usable registration, brand or generic name; not treated as a clean `NO_MATCH` |
| 6 | MANUAL_REVIEW_REQUIRED | constructed consolidated OCR with two different brand values | `MANUAL_REVIEW_REQUIRED` | `brand_name` field is `CONFLICT`, both raw values retained; `Manual review required: YES` |
| 7 | GENERIC-NAME COLLISION | `check Paracetamol` | `MANUAL_REVIEW_REQUIRED` | Two products retained (`AC-Mol Drops`, `Acepol Suspension`); no first-row selection; no candidate marked `SELECTED` |
| 8 | PACKAGING RECONCILIATION | all 11 rows of `package_results.csv` | `NO_MATCH` x8, `MANUAL_REVIEW_REQUIRED` x3 | `pack_01` and `pack_04` are ambiguity reviews; `pack_10` retains a genuine brand conflict; **no package is forced to `MATCH`** |

Final banner:

```text
Scenarios shown: 8 (scenario 8 contains 11 package records)
Statuses observed: MATCH, PARTIAL_MATCH, MISMATCH, NO_MATCH, INSUFFICIENT_INFORMATION, MANUAL_REVIEW_REQUIRED
All results were produced by the frozen offline engine; none were fabricated.
```

### Reading the output correctly

- `PRESENT` means a usable value; `MISSING` means not supplied; `NOT_VISIBLE`
  means the source explicitly said the value could not be read; `CONFLICT`
  means two incompatible original values were retained.
- Field statuses `MATCH`, `MISMATCH`, `UNKNOWN`, `UNPARSED`, `CONFLICT` are
  distinct. `UNKNOWN` is missing information, **not** a mismatch.
- `Manual review required: YES` appears for scenarios 6 and 7 and for
  `pack_01`, `pack_04`, `pack_10`.
- `similarity_score` is printed only as a retrieval hint. It is never called a
  confidence, probability or percentage, and it never decides identity.
- In scenario 7 the SMS adapter has a single name field, so field comparisons
  against each retained candidate can show `brand_name = MISMATCH` while
  retrieval correctly used the text as a generic name. This is an honest
  consequence of the existing adapter; the decision remains "retain all
  candidates, ask a human", and no candidate is selected.

---

## 6. What each demonstration proves

| Part | Proves |
| --- | --- |
| Scenario 1 | Exact registration lookup is deterministic and outranks name evidence; unknown supporting fields stay unknown rather than being guessed |
| Scenario 2 | A single exact brand hit with no independent support is `PARTIAL_MATCH`, not an authenticity claim |
| Scenario 3 | A conflicting observed field produces `MISMATCH` even when a registration number is exact; other name-based candidates are retained for transparency |
| Scenario 4 | An unknown registration number yields `NO_MATCH` and cannot be turned into a fuzzy name guess |
| Scenario 5 | "Insufficient information" is a separate decision from "no match" |
| Scenario 6 | A genuine observation conflict routes to manual review and preserves both raw values |
| Scenario 7 | Generic-name collisions preserve every matching product; no arbitrary first-row selection |
| Scenario 8 | The same engine processes all 11 preserved packaging records offline; OCR values stay observations, and no packaging row is falsely accepted |
| Optional live section | The explanation layer can be called with bounded time and synthetic findings, and degrades safely when Gemini is unavailable |

---

## 7. What the demonstration does NOT prove

1. **Not real-world OCR accuracy.** Ground truth is empty; real-pack OCR
   accuracy is **NOT TESTED**. Every packaging result prints
   `Accuracy tested: False`.
2. **Not authoritative regulatory data.** The 40-row catalogue is a
   deterministic test catalogue with source URLs, not a live NAFDAC feed.
3. **Not authenticity.** The engine never states that a medicine is genuine,
   fake, safe, approved, banned or recalled.
4. **Not backend integration.** `src/contracts.py` is still
   `PROPOSED / AWAITING BACKEND CONFIRMATION` and
   `AWAITING_BACKEND_CONFIRMATION = True`. Nothing here wires a backend.
5. **Not a numeric confidence claim.** No confidence, probability or success
   percentage is emitted; `similarity_score` is a string-similarity hint only.
6. **Not full live validation.** Live Gemini validation is `PARTIAL`; the demo
   makes at most one bounded explanation call and is not a substitute for the
   opt-in live suite (`python -m pytest -q tests/live --run-live`).
7. **Not a medical advice tool.** No dosage, interaction or treatment advice is
   generated.

---

## 8. Files involved

Created for this demonstration:

- `tools/demo.py`
- `docs/COMPETITION_DEMO_GUIDE.md`

Read but not modified:

- all `src/` verification modules, `src/contracts.py`, `src/gemini.py`
- `data/test_drugs.csv`, `data/packaging/package_results.csv`
- `.env` (only via the existing loader in the optional `--live` path)

No original packaging image, OCR source record, ground-truth file, or frozen
verification logic was changed.

---

## 9. Troubleshooting

| Problem | Action |
| --- | --- |
| `python` not recognised | Use `py -3 tools/demo.py` |
| Missing `pydantic` / `rapidfuzz` | Run `python -m pip install -r requirements.txt` |
| Garbled Unicode in console | The script already forces UTF-8 with replacement; if a wrapper strips it, run `chcp 65001` first |
| `--live` reports unavailable | Expected offline behaviour; the offline section is already complete and the script exits normally |
| Need to reset after live rehearsal | `Remove-Item Env:\AI_ML_MOCK` |
