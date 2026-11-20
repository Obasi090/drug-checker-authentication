# Verification Engine Performance Audit - Stage 5.3

Date: 19 Nov 2026
Data: the preserved 40-record catalogue and 11 packaging records. All decisions
below came from `VerificationEngine.verify()` / `verify_package_results()` in a
single deterministic process. No expected result was invented from thin air;
cases without an independent expected value are labelled **functional demonstration**.

## 1. Execution time

| Workload | Cases | Total time | Slowest single case |
| --- | ---: | ---: | ---: |
| 13 targeted engine probes | 13 | 13.87 ms | 4.544 ms (fuzzy generic with 3 candidates) |
| Packaging batch | 11 | 13.78 ms | n/a (batch) |
| Packaging reconciliation (separate) | 22 OCR rows → 11 medicines | 2.04 ms | n/a |

These are local, in-process timings on this Windows 11 machine. They are **not**
a benchmark of a deployed service, and no throughput claim is made.

## 2. Required evaluation areas

| # | Area | Test used | Observed behaviour | Classification |
| --- | --- | --- | --- | --- |
| 1 | Exact registration matching | `check B4-1180` | `MATCH`, candidate `CAT-0002` (`1980 Azithromycin USP 250 mg Tablets [B4-1180]`), 1 candidate, 0.725 ms; generic/manufacturer/dosage form stayed `UNKNOWN` | Functional demonstration; expected behaviour from documented design |
| 2 | Exact brand matching | `check Acimox Capsule` | `PARTIAL_MATCH`, `CAT-0036`, 0.642 ms; no independent corroboration so not promoted to `MATCH` | Functional demonstration |
| 3 | Generic-name matching | observation with `generic_name="Gabapentin"` | Candidate `Ablept 300 Capsules [B4-9460]` retrieved by `generic_name_exact`, but status `MANUAL_REVIEW_REQUIRED` with reason "exact generic-name match with colliding products … requires explicit confirmation" | Safety behaviour confirmed for this catalogue; not a general accuracy result |
| 4 | Duplicate generic handling | `check Paracetamol` | `MANUAL_REVIEW_REQUIRED`, 2 retained candidates, `selected_product_id=None`, no candidate marked selected, 0.883 ms | Functional demonstration; all products preserved |
| 5 | Fuzzy brand matching | `check Ablept 300 Capusles` | 1 candidate, `matched_by=fuzzy_brand_name`, similarity_score 94.7, `requires_confirmation=True`, status `MANUAL_REVIEW_REQUIRED`, 1.249 ms | Functional demonstration; score is a retrieval hint only |
| 6 | Fuzzy generic matching | `check Amoxicilin Trihydrate` | 3 ambiguous candidates (85.7 / 81.4 / 81.4), `selected=None`, 4.544 ms | Functional demonstration; ambiguity preserved |
| 7 | Registration mismatch | reg `B4-1180` + generic `Gabapentin` | `MISMATCH`, selected `CAT-0002`, 2 candidates retained, `review_fields=['generic_name']`, 1.609 ms | Functional demonstration |
| 8 | Brand mismatch | reg `B4-1180` + brand `Unrelated Product ZZZ` | `MISMATCH`, 1 candidate, `review_fields=['brand_name']`, 1.478 ms | Functional demonstration |
| 9 | Strength mismatch | reg `B4-1180` + strength `999 mg` | `MISMATCH`, `review_fields=['strength']`, 0.807 ms | Functional demonstration |
| 10 | Manufacturer mismatch | reg `B4-1180` + manufacturer `Wrong Maker Ltd` | `MISMATCH`, `review_fields=['manufacturer']`, 0.611 ms | Functional demonstration |
| 11 | Missing information | `hello` | `INSUFFICIENT_INFORMATION`, 0 candidates, 0.118 ms; not silently converted to `NO_MATCH` | Functional demonstration; separate status confirmed |
| 12 | Conflicting observations | reg `B4-1180` + conflicting brand values | `MANUAL_REVIEW_REQUIRED`, both raw values retained, `review_fields=['brand_name']`, 0.425 ms | Functional demonstration; conflict is not averaged away |
| 13 | Package volume vs strength | reg `B4-1180` + strength `250 mg` + volume `100 ml` | `MATCH`, 0.375 ms; volume did not overwrite or mimic strength | Functional demonstration; field separation confirmed |
| 14 | Multiple candidates | cases 4 and 6 above | 2 and 3 candidates retained respectively; no arbitrary first-row selection; no confirmation granted | Functional demonstration |
| 15 | All six decisions | union of the 13 probes plus packaging batch | `MATCH`, `PARTIAL_MATCH`, `MISMATCH`, `NO_MATCH`, `INSUFFICIENT_INFORMATION`, `MANUAL_REVIEW_REQUIRED` all observed | Verified |

Packaging batch detail: 11 results, 8 `NO_MATCH` and 3 `MANUAL_REVIEW_REQUIRED`
(`pack_01`, `pack_04`, `pack_10`), zero `MATCH`, 13.78 ms. This is the correct safe
outcome because none of the three packaging registration numbers occurs in the
test catalogue. `pack_10` retains its manual-review requirement.

## 3. Candidate retrieval behaviour

- Exact registration wins and suppresses fuzzy name substitution.
- An unknown, well-formed registration (`ZZ-9999`) produces `NO_MATCH`; fuzzy name
  suggestions are suppressed rather than forcing a plausible-looking product.
- Exact brand returns one candidate but only `PARTIAL_MATCH` without corroboration.
- Exact generic returns **every** matching product and requires confirmation even
  when only one exists in this catalogue.
- Fuzzy retrieval returns candidates with scores and `requires_confirmation=True`;
  it never sets `MATCH` on its own.
- Retrieval paths are merged per product, so one product is not counted twice.
- No candidate is ever silently substituted for the user's stated identity.

## 4. Safety observations

| Check | Result |
| --- | --- |
| Missing fields remain `UNKNOWN` | Yes - case 1 explicitly shows generic, manufacturer and dosage form as missing, not mismatched |
| Mismatch fields are separated from missing fields | Yes - `MISMATCH` and `UNKNOWN` are distinct statuses in all probes |
| Conflicts force manual review | Yes - case 12 and `pack_10` |
| Conflicting raw values preserved | Yes - both brand values retained in the observation and result |
| Fuzzy score treated as identity | No - score printed only as a retrieval hint |
| Confidence / probability / percentage emitted | No - none of the 24 results contained such a value |
| Forced packaging `MATCH` | No - 0 of 11 |
| Automatic acceptance of generic name | No - all generic cases require confirmation |
| Accuracy claim | Never - every result carries `accuracy_tested=False` |

## 5. No invented accuracy

There is no independently verified expected outcome for most of the 13 targeted
cases, so they are **functional demonstrations**, not accuracy measurements. The
packaging records have empty ground truth (0/11 on all four primary fields), so
the engine's `evaluate_ground_truth()` correctly returns `NOT TESTED` with 0 scored
and 44 skipped fields. Any accuracy percentage presented for this stage would be
fabricated and is therefore deliberately absent.

## 6. Status classification

- **IMPLEMENTED:** all 15 evaluation areas have working code paths.
- **TESTED OFFLINE:** every case in this document; 182 passing offline tests.
- **TESTED LIVE:** not applicable to the deterministic engine; no live call is
  needed for a verification decision.
- **PARTIALLY VALIDATED:** generic/fuzzy behaviour is validated against this
  40-record catalogue only.
- **NOT VALIDATED:** accuracy against authoritative or independently verified data.
- **PENDING BACKEND INTEGRATION:** the engine has no backend consumer and the
  proposed contract remains unconfirmed.
