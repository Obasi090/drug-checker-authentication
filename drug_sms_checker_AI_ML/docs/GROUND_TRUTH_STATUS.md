# Ground Truth Status — 19 Nov 2026

## Current state

`data/packaging/ground_truth.csv` was preserved unchanged.

| Field | Populated rows |
| --- | ---: |
| medicine_id | 11 / 11 |
| brand_name | 0 / 11 |
| registration_number | 0 / 11 |
| manufacturer | 0 / 11 |
| strength | 0 / 11 |

There is no package-volume verification column, so package volume cannot be scored even after the four primary fields are verified.

## What must not populate ground truth

Ground truth may only be filled by independent verification from the actual physical medicine packaging. It must **not** be filled from:

- Gemini extraction results
- `ocr_results.csv`
- `package_results.csv`
- guessed manufacturer names
- online assumptions
- inferred registration numbers
- another medicine's label

Gemini and consolidated outputs are candidates for comparison, never the expected value.

## Evaluation workflow safety

`src/packaging.evaluate_ground_truth()` only scores fields whose ground-truth value is populated. Missing fields are excluded from scoring. If no verified field exists, the report is explicitly `NOT TESTED` and contains no accuracy percentage.

Current output of `python tools/photo_eval.py`:

```text
template: photo_test_template.csv
captures: 22 | packs: 11 | lighting: ['daylight', 'indoor_tube_light']
ground truth: NOT TESTED
verified fields: 0 | excluded fields: 44
REAL-PACK OCR ACCURACY: NOT TESTED
reason: no independently verified ground-truth field is populated;
        Gemini/consolidated outputs must never be used as ground truth.
```

The 44 excluded fields are 11 medicines × 4 primary fields.

## Required future process

1. Inspect each physical pack independently.
2. Record exactly readable values in `ground_truth.csv` for `brand_name`, `registration_number`, `manufacturer` and `strength`.
3. Record the reviewer and verification date in a separate provenance record; do not infer them from OCR.
4. Leave unverifiable fields empty rather than guessing.
5. Re-run `python tools/photo_eval.py`.
6. Only then may field-level OCR results be calculated, and the result must still show how many fields were excluded.

Until that process is completed, the only valid claim is: **REAL-PACK OCR ACCURACY: NOT TESTED**.
