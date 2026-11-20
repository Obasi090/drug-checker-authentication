# Packaging Dataset Validation — 19 Nov 2026

## Scope

This validation covers the packaging image folders and the three packaging CSVs:

- `data/packaging/daylight/`
- `data/packaging/indoor/`
- `data/packaging/ocr_results.csv`
- `data/packaging/package_results.csv`
- `data/packaging/ground_truth.csv`

No image was renamed, deleted or modified. No live Gemini request was made.

Backups created before changes:

- `data/packaging/ocr_results.original.csv`
- `data/packaging/package_results.pre_reconciliation.csv`

## Pack-count decision

Actual folders contain:

- 11 daylight image files: `pack_01.jpeg` … `pack_11.jpeg`
- 11 indoor image files: `pack_01..jpeg`, `pack_02.jpeg` … `pack_11.jpeg`

There is **no complete `pack_12`** pair, no `pack_12` OCR rows and no `pack_12` ground-truth row. The project is therefore standardised on the **11 existing medicine IDs**, not 12.

## Filename mapping

Image files were matched by `medicine_id` and lighting condition against the actual directory listing. `image_filename` in `ocr_results.csv` was corrected only where the corresponding actual file could be identified. All other OCR fields were left unchanged.

| medicine_id | daylight_filename | indoor_filename | daylight_exists | indoor_exists | validation_status |
| --- | --- | --- | --- | --- | --- |
| pack_01 | pack_01.jpeg | pack_01..jpeg | yes | yes | VALID — both filenames corrected |
| pack_02 | pack_02.jpeg | pack_02.jpeg | yes | yes | VALID — both filenames corrected |
| pack_03 | pack_03.jpeg | pack_03.jpeg | yes | yes | VALID — both filenames corrected |
| pack_04 | pack_04.jpeg | pack_04.jpeg | yes | yes | VALID — indoor corrected, daylight unchanged |
| pack_05 | pack_05.jpeg | pack_05.jpeg | yes | yes | VALID — both filenames corrected |
| pack_06 | pack_06.jpeg | pack_06.jpeg | yes | yes | VALID — both filenames corrected |
| pack_07 | pack_07.jpeg | pack_07.jpeg | yes | yes | VALID — both filenames corrected |
| pack_08 | pack_08.jpeg | pack_08.jpeg | yes | yes | VALID — both filenames corrected |
| pack_09 | pack_09.jpeg | pack_09.jpeg | yes | yes | VALID — both filenames corrected |
| pack_10 | pack_10.jpeg | pack_10.jpeg | yes | yes | VALID — both filenames corrected |
| pack_11 | pack_11.jpeg | pack_11.jpeg | yes | yes | VALID — both filenames corrected |

`pack_01..jpeg` contains a double dot. It is the actual filename on disk and was **not** renamed. `.jpg` was not assumed to be interchangeable with `.jpeg`; the recorded value now matches the real file exactly.

## Original-to-corrected filename references

21 of 22 filename references were corrected. `pack_04` daylight was already correct.

| medicine_id | condition | original recorded value | corrected actual filename |
| --- | --- | --- | --- |
| pack_01 | daylight | pack_01.jpg (assumed) | pack_01.jpeg |
| pack_01 | indoor | pack_01 indoor image (filename not supplied) | pack_01..jpeg |
| pack_02 | daylight | pack_02 daylight image (filename not supplied) | pack_02.jpeg |
| pack_02 | indoor | pack_02 indoor image (filename not supplied) | pack_02.jpeg |
| pack_03 | daylight | pack_03 daylight image | pack_03.jpeg |
| pack_03 | indoor | pack_03 indoor image | pack_03.jpeg |
| pack_04 | indoor | pack_04_2.jpeg (described once as pack_04.jpeg; confirm filename) | pack_04.jpeg |
| pack_05 | daylight | pack_05 daylight image | pack_05.jpeg |
| pack_05 | indoor | pack_05 indoor image | pack_05.jpeg |
| pack_06 | daylight | pack_06 daylight image | pack_06.jpeg |
| pack_06 | indoor | pack_06 indoor image | pack_06.jpeg |
| pack_07 | daylight | pack_07 daylight image | pack_07.jpeg |
| pack_07 | indoor | pack_07 indoor image | pack_07.jpeg |
| pack_08 | daylight | pack_08 daylight image | pack_08.jpeg |
| pack_08 | indoor | pack_08 indoor image | pack_08.jpeg |
| pack_09 | daylight | pack_09 daylight image | pack_09.jpeg |
| pack_09 | indoor | pack_09 indoor image | pack_09.jpeg |
| pack_10 | daylight | pack_10 daylight image | pack_10.jpeg |
| pack_10 | indoor | pack_10 indoor image | pack_10.jpeg |
| pack_11 | daylight | pack_11 daylight image | pack_11.jpeg |
| pack_11 | indoor | pack_11 indoor image | pack_11.jpeg |

## Integrity results

| Check | Result |
| --- | --- |
| Medicine IDs in OCR CSV | 11 |
| Image-level OCR records | 22 |
| Daylight records / indoor records | 11 / 11 |
| Duplicate `(medicine_id, image_condition)` | 0 |
| Medicine IDs aligned across OCR, package and ground-truth CSVs | Yes |
| Actual image files | 22 |
| Missing images after filename correction | 0 |
| Unmatched image files | 0 |
| OCR records whose filename is absent on disk | 0 |
| Non-filename OCR fields modified | 0 |

## Related changes

- `tests/photo_test_template.csv` now uses `PACK-01` … `PACK-11` (22 captures) instead of 12 packs.
- `tests/test_photo.py`, `tools/photo_eval.py` and related documentation now reflect the 11-pack dataset.
- Regenerate the derived reconciliation at any time with:

```powershell
python tools\reconcile_packaging.py
```
