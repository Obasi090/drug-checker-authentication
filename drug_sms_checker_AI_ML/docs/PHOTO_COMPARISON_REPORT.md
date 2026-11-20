# Photo Comparison Report — 19 Nov 2026

## What this report is

This is a **multi-image extraction comparison** over the preserved image-level OCR records. It measures whether daylight and indoor extractions agree, differ meaningfully, or are unreadable.

It is **not** an OCR accuracy report. Agreement between two extractions does not prove either value is correct. No OCR accuracy percentage is claimed. Ground truth remains empty; see `docs/GROUND_TRUTH_STATUS.md`.

## Inputs and scope

- Source: `data/packaging/ocr_results.csv` (22 image-level records)
- Output: `data/packaging/package_results.csv` (11 consolidated medicine records)
- Medicines: 11
- Images: 22 (11 daylight + 11 indoor)
- Fields compared independently: `brand_name`, `registration_number`, `manufacturer`, `strength`
- Package volume is kept separately as `package_volume`; it is never treated as strength.

## Reconciliation rules applied

| Status | Meaning |
| --- | --- |
| `CONSISTENT` | Both images contain the same readable value (harmless case/whitespace/punctuation differences are ignored for brand/manufacturer). |
| `DAYLIGHT_ONLY` | Daylight is readable; indoor is missing/unreadable. Daylight value is retained. |
| `INDOOR_ONLY` | Indoor is readable; daylight is missing/unreadable. Indoor value is retained. |
| `NOT_VISIBLE` | Both images are missing/unreadable. Canonical value is `not visible`. |
| `CONFLICT` | Both images contain different readable values. No value is chosen automatically. |

Missing or unreadable is **not** a conflict. Canonical missing representation in generated data is lowercase `not visible`.

For a conflict, the primary column contains the explicit marker `CONFLICT`; the exact competing original values are stored in the corresponding `*_conflict_daylight` and `*_conflict_indoor` columns. The marker is a status, not an extracted fact.

## Aggregate comparison results

| Field | CONSISTENT | DAYLIGHT_ONLY | INDOOR_ONLY | NOT_VISIBLE | CONFLICT |
| --- | ---: | ---: | ---: | ---: | ---: |
| brand_name | 10 | 0 | 0 | 0 | 1 |
| registration_number | 1 | 2 | 0 | 8 | 0 |
| manufacturer | 5 | 0 | 1 | 5 | 0 |
| strength | 1 | 0 | 0 | 10 | 0 |
| package_volume (separate metadata) | 5 | 0 | 2 | 4 | 0 |

### One-sided readable fields

| Medicine | Field | Status | Retained value |
| --- | --- | --- | --- |
| pack_05 | manufacturer | `INDOOR_ONLY` | New Healthway Co. Limited |
| pack_10 | registration_number | `DAYLIGHT_ONLY` | 04-1860 |
| pack_11 | registration_number | `DAYLIGHT_ONLY` | 04-3230 |

Package-volume visibility differences, recorded separately:

| Medicine | Status | Retained value |
| --- | --- | --- |
| pack_05 | `INDOOR_ONLY` | 200 ml |
| pack_06 | `INDOOR_ONLY` | 100 ml |

### Genuine conflicts

| Medicine | Field | Daylight value | Indoor value | Review required |
| --- | --- | --- | --- | --- |
| pack_10 | brand_name | Bode Sudrex (Headache & Fever — Paracetamol, Caffeine; Two-Layer Tablets) | Bode Sudrex (Headache & Fever — Paracetamol, Caffeine) | Yes |

The pack_10 difference is the meaningful extra description `Two-Layer Tablets`, not merely punctuation or spacing. It is therefore recorded for review and was not silently resolved.

The registration difference on pack_10 is **not** a conflict: daylight reads `04-1860` and indoor says `Not visible`, so the daylight value is retained with status `DAYLIGHT_ONLY`.

### Manual review cases

| Medicine | manual_review_required | manual_review_fields | Reason |
| --- | --- | --- | --- |
| pack_10 | `true` | `brand_name` | Both images contain different readable brand descriptions. |

All other medicines have `manual_review_required = false`. In particular:

- `pack_05` manufacturer is `INDOOR_ONLY`, not a conflict.
- `pack_06` package volume is `INDOOR_ONLY`, not a conflict.
- `pack_11` registration number is `DAYLIGHT_ONLY`, not a conflict.

## Per-medicine summary

`C` = CONSISTENT, `D` = DAYLIGHT_ONLY, `I` = INDOOR_ONLY, `N` = NOT_VISIBLE, `X` = CONFLICT.

| medicine_id | brand | registration | manufacturer | strength | package_volume | Review |
| --- | --- | --- | --- | --- | --- | --- |
| pack_01 | C | N | C | N | N | no |
| pack_02 | C | C | C | C | N | no |
| pack_03 | C | N | N | N | C | no |
| pack_04 | C | N | C | N | C | no |
| pack_05 | C | N | I | N | I | no |
| pack_06 | C | N | N | N | I | no |
| pack_07 | C | N | N | N | C | no |
| pack_08 | C | N | C | N | C | no |
| pack_09 | C | N | N | N | N | no |
| pack_10 | X | D | N | N | N | yes — brand_name |
| pack_11 | C | D | C | N | C | no |

## Missing information

Of the 44 primary field slots (11 medicines × 4 fields), 23 are `NOT_VISIBLE`:

- brand_name: 0
- registration_number: 8
- manufacturer: 5
- strength: 10

These gaps are comparison gaps, not accuracy verdicts. They must be resolved only by independently verified physical-pack inspection.

## Reproduction

```powershell
python tools\reconcile_packaging.py
python -m pytest -q tests/test_packaging.py tests/test_ground_truth.py
```
