"""Reproducible, offline-first demonstration of the frozen verification engine.

Usage:
    python tools/demo.py            offline demonstration only (default)
    python tools/demo.py --live     offline demonstration plus optional live Gemini

The offline path uses only the local catalogue and existing engine modules. It
makes no network calls and writes no files. The optional --live path exercises
only the Gemini *explanation* layer with a clearly synthetic record; it is
guarded so an unavailable API can never prevent the offline demonstration.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.decision import FIELD_LABELS, VERIFICATION_STATUSES  # noqa: E402
from src.observation import (  # noqa: E402
    OBSERVED_FIELDS,
    MedicineObservation,
    ObservedField,
    observation_from_sms_text,
)
from src.packaging import read_csv_rows  # noqa: E402
from src.verification import DEFAULT_PACKAGE_RESULTS, VerificationEngine, VerificationResult  # noqa: E402

LINE = "=" * 78
SUB = "-" * 78


@dataclass(frozen=True)
class DemoCase:
    number: int
    title: str
    original_input: str
    observation: MedicineObservation
    result: VerificationResult


def configure_console() -> None:
    """Keep Unicode catalogue text safe on Windows console code pages."""
    stream = getattr(sys.stdout, "reconfigure", None)
    if stream is not None:
        try:
            stream(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            pass


def label(name: str) -> str:
    return FIELD_LABELS.get(name, name)


def labels(names: list[str]) -> str:
    return ", ".join(label(name) for name in names) if names else "none"


def build_sms_cases(engine: VerificationEngine) -> list[DemoCase]:
    """Build scenarios 1-7 from the real catalogue and real observation adapters."""
    names = engine.catalogue.brand_names

    def sms(number: int, title: str, text: str, observation_id: str) -> DemoCase:
        observation = observation_from_sms_text(
            text, names, observation_id=observation_id
        )
        return DemoCase(
            number=number,
            title=title,
            original_input=f'SMS text: "{text}"',
            observation=observation,
            result=engine.verify(observation),
        )

    cases = [
        sms(1, "MATCH - exact registration number",
            "check B4-1180", "DEMO-01-MATCH"),
        sms(2, "PARTIAL_MATCH - right brand, incomplete evidence",
            "check Acimox Capsule", "DEMO-02-PARTIAL"),
    ]

    mismatch_obs = MedicineObservation(
        observation_id="DEMO-03-MISMATCH",
        source_channel="sms",
        registration_number=ObservedField.present("B4-1180", "constructed input"),
        generic_name=ObservedField.present("Gabapentin", "constructed input"),
    )
    cases.append(DemoCase(
        number=3,
        title="MISMATCH - conflicting product information",
        original_input=(
            'Constructed observation: registration_number="B4-1180"; '
            'generic_name="Gabapentin"'
        ),
        observation=mismatch_obs,
        result=engine.verify(mismatch_obs),
    ))

    cases.append(sms(4, "NO_MATCH - unknown registration number",
                     "check ZZ-9999", "DEMO-04-NO-MATCH"))
    cases.append(sms(5, "INSUFFICIENT_INFORMATION - no identity fields",
                     "hello", "DEMO-05-INSUFFICIENT"))

    conflict_obs = MedicineObservation(
        observation_id="DEMO-06-REVIEW",
        source_channel="consolidated_ocr",
        registration_number=ObservedField.present("B4-1180", "constructed OCR input"),
        brand_name=ObservedField.conflict(
            "1980 Azithromycin USP 250 mg Tablets",
            "Ablept 300 Capsules",
            "constructed daylight/indoor OCR conflict",
        ),
    )
    cases.append(DemoCase(
        number=6,
        title="MANUAL_REVIEW_REQUIRED - conflicting observation",
        original_input=(
            'Constructed consolidated OCR: registration_number="B4-1180"; '
            'brand_name conflict "1980 Azithromycin USP 250 mg Tablets" vs '
            '"Ablept 300 Capsules"'
        ),
        observation=conflict_obs,
        result=engine.verify(conflict_obs),
    ))

    cases.append(sms(7, "GENERIC-NAME COLLISION - Paracetamol",
                     "check Paracetamol", "DEMO-07-COLLISION"))
    return cases


def render_observed(observation: MedicineObservation) -> None:
    print("OBSERVED MEDICINE INFORMATION")
    for name in OBSERVED_FIELDS:
        field = observation.field(name)
        if field.status == "PRESENT":
            value = str(field.value)
        elif field.status == "CONFLICT":
            value = f"CONFLICT -> {field.raw}"
        elif field.status == "NOT_VISIBLE":
            value = f"not visible (raw={field.raw!r})" if field.raw else "not visible"
        else:
            value = "(missing - not supplied)"
        print(f"  {label(name):<22}: {value}   [{field.status}]")
    print(f"  {'channel':<22}: {observation.source_channel}")


def render_candidates(result: VerificationResult) -> None:
    print("CATALOGUE CANDIDATES")
    candidate_set = result.candidates
    print(f"  fuzzy suggestions used: {candidate_set.fuzzy_suggestions_used}")
    if not candidate_set.candidates:
        print("  (none retrieved)")
        for reason in candidate_set.reasons:
            print(f"    - {reason}")
        return
    for index, candidate in enumerate(candidate_set.candidates, start=1):
        flag = "SELECTED" if candidate.product.product_id == result.selected_product_id else "RETAINED (not selected)"
        print(f"  [{index}] {candidate.identity_label} -- {flag}")
        print(f"      matched_by      : {candidate.matched_by}")
        print(f"      matched_paths   : {', '.join(candidate.matched_paths)}")
        score = candidate.similarity_score
        score_text = "n/a" if score is None else f"{score:.1f}"
        print(f"      similarity_score: {score_text}  (retrieval hint only; NOT a probability or confidence)")
        for reason in candidate.reasons:
            print(f"      - {reason}")
    for reason in candidate_set.reasons:
        print(f"  note: {reason}")


def render_comparisons(result: VerificationResult) -> None:
    print("RELEVANT FIELD COMPARISONS")
    if not result.field_comparisons:
        print("  (none - no catalogue candidate was retrieved, so no field comparison was performed)")
        return
    names = {
        candidate.product.product_id: candidate.identity_label
        for candidate in result.candidates.candidates
    }
    for product_id, comparisons in result.field_comparisons.items():
        print(f"  Candidate: {names.get(product_id, product_id)}")
        for item in comparisons:
            observed = item.observed_raw if item.observed_raw is not None else "(none)"
            catalogue = item.catalogue_raw if item.catalogue_raw is not None else "(blank)"
            print(f"    {label(item.field):<20}: {item.status}")
            print(f"        observed ={observed!r}")
            print(f"        catalogue={catalogue!r}")
            print(f"        why      : {item.reason}")
            if item.similarity_score is not None:
                print(f"        similarity_score={item.similarity_score:.1f} (supporting hint only)")


def render_decision(result: VerificationResult) -> None:
    print("FINAL DECISION")
    print(f"  Status                 : {result.status}")
    print(f"  Meaning                : {result.status_explanation}")
    print(f"  Manual review required : {'YES' if result.is_manual_review else 'NO'}")
    print("  Reasons:")
    for reason in result.reasons:
        print(f"    - {reason}")
    print(f"  Missing information    : {labels(result.missing_fields)}")
    print(f"  Fields needing review  : {labels(result.review_fields)}")
    print(f"  Accuracy tested        : {result.accuracy_tested} (real-pack OCR accuracy: NOT TESTED)")


def render_case(case: DemoCase) -> None:
    print()
    print(LINE)
    print(f"SCENARIO {case.number}: {case.title}")
    print(LINE)
    print(f"Original input: {case.original_input}")
    print()
    render_observed(case.observation)
    print()
    render_candidates(case.result)
    print()
    render_comparisons(case.result)
    print()
    render_decision(case.result)


def render_package_scenario(engine: VerificationEngine) -> list[VerificationResult]:
    """Scenario 8: all 11 reconciled packaging rows, without touching source data."""
    rows = read_csv_rows(DEFAULT_PACKAGE_RESULTS)
    observations = [
        MedicineObservation.from_package_result(row) for row in rows
    ]
    results = engine.verify_package_results()
    if [obs.observation_id for obs in observations] != [res.observation_id for res in results]:
        raise RuntimeError("package observations and results are not aligned")

    counts = Counter(result.status for result in results)
    print()
    print(LINE)
    print("SCENARIO 8: PACKAGING IMAGE RECONCILIATION (11 existing records)")
    print(LINE)
    print("Original input: existing rows in data/packaging/package_results.csv")
    print("Ground truth is empty; OCR values are observations only.")
    print("Decisions: " + ", ".join(f"{name}={counts[name]}" for name in sorted(counts)))

    for observation, result in zip(observations, results):
        print()
        print(SUB)
        print(f"{result.observation_id} -> {result.status}")
        print(SUB)
        medicine_id = result.provenance.get("medicine_id", "")
        print(f"  Original input: package row medicine_id={medicine_id!r}")
        details: list[str] = []
        for name in OBSERVED_FIELDS:
            field = observation.field(name)
            if field.status == "PRESENT":
                details.append(f"{label(name)}={field.value!r}")
            elif field.status == "CONFLICT":
                details.append(f"{label(name)}=CONFLICT({field.raw})")
            elif field.status == "NOT_VISIBLE":
                details.append(f"{label(name)}=not visible")
            else:
                details.append(f"{label(name)}=missing")
        print("  Observed: " + "; ".join(details))
        candidates = [candidate.identity_label for candidate in result.candidates.candidates]
        print("  Candidates: " + (", ".join(candidates) if candidates else "(none retrieved)"))
        comparison_count = sum(len(items) for items in result.field_comparisons.values())
        if not comparison_count:
            comparison_text = "(none - no candidate was retrieved)"
        elif result.selected_product_id is None:
            comparison_text = f"{comparison_count} row(s) across retained candidates (none selected)"
        else:
            comparison_text = f"{comparison_count} row(s) against the selected candidate"
        print("  Field comparisons: " + comparison_text)
        print(f"  Final decision: {result.status}")
        print(f"  Manual review required: {'YES' if result.is_manual_review else 'NO'}")
        print(f"  Explanation: {result.status_explanation}")
        for reason in result.reasons:
            print(f"    - {reason}")
        if result.review_fields:
            print("  Review fields: " + labels(result.review_fields))
        print("  Accuracy tested: False (real-pack OCR accuracy: NOT TESTED)")
    return results


def print_header(engine: VerificationEngine) -> None:
    print(LINE)
    print("DRUG SMS CHECKER - REPRODUCIBLE OFFLINE DEMONSTRATION")
    print(LINE)
    print("Implementation: FROZEN | Default mode: OFFLINE (no network calls)")
    print(f"Catalogue: {engine.catalogue.source_path} ({len(engine.catalogue.products)} rows)")
    print(f"Catalogue SHA-256: {engine.catalogue.source_sha256}")
    print("Decision statuses: " + ", ".join(VERIFICATION_STATUSES))
    print("This is a deterministic test catalogue, NOT an authoritative regulatory database.")
    print("No confidence, probability or percentage is emitted; similarity_score is a retrieval hint only.")


def run_offline_demo() -> None:
    engine = VerificationEngine()
    print_header(engine)
    cases = build_sms_cases(engine)
    for case in cases:
        render_case(case)
    package_results = render_package_scenario(engine)

    seen = {case.result.status for case in cases}
    seen.update(result.status for result in package_results)
    print()
    print(LINE)
    print("DEMONSTRATION COMPLETE")
    print(LINE)
    print(f"Scenarios shown: {len(cases) + 1} (scenario 8 contains {len(package_results)} package records)")
    print("Statuses observed: " + ", ".join(name for name in VERIFICATION_STATUSES if name in seen))
    print("All results were produced by the frozen offline engine; none were fabricated.")


def run_live_demo() -> None:
    """Optional, bounded explanation-layer check. Failure never blocks offline output."""
    print()
    print(LINE)
    print("OPTIONAL LIVE GEMINI DEMONSTRATION (explanation layer only)")
    print(LINE)
    try:
        from src.contracts import adapt_findings
        from src.gemini import GeminiClient

        client = GeminiClient()
    except Exception as exc:  # missing dependency, malformed environment, etc.
        print(f"  Skipped: Gemini client unavailable ({type(exc).__name__}).")
        print("  The offline demonstration above is unaffected.")
        return

    print(f"  Configured model: {client.model}")
    print(f"  Gemini available: {client.available} (API key is never printed)")
    if not client.available:
        print("  Skipped: no usable GEMINI_API_KEY, or mock mode is enabled.")
        print("  The offline demonstration above is unaffected.")
        return

    try:
        findings = adapt_findings({
            "query": "DEMO Product Alpha",
            "query_type": "name",
            "status": "found",
            "matches":[{
                "reg_number": "ZZ-1234",
                "brand_name": "DEMO Product Alpha",
                "generic_name": "Synthetic molecule",
                "manufacturer": "Fictional Pharma Ltd",
                "strength": "100 mg",
                "registry_status": "SYNTHETIC TEST RECORD",
                "source": "SYNTHETIC TEST RECORD",
            }],
            "alerts": [],
            "mismatches": [],
            "data_as_of": "19 Nov 2026 (synthetic)",
        })
    except Exception as exc:
        print(f"  Skipped: could not build synthetic findings ({type(exc).__name__}).")
        return

    print("  Findings: SYNTHETIC TEST RECORD only; no real medicine is described.")
    try:
        explanation = client.explain(
            "Summarise the supplied synthetic record for DEMO Product Alpha.",
            findings,
        )
    except Exception as exc:
        print(f"  Gemini unavailable: {type(exc).__name__}.")
        print("  The offline demonstration above is unaffected.")
        return

    print(f"  Reply: {explanation.reply}")
    print(f"  used_mock={explanation.used_mock} | used_fallback={explanation.used_fallback}")
    print("  Bounded: one explain() call; SDK timeout 15 s with at most 2 attempts.")
    print("  This does NOT verify a medicine and is NOT backend integration approval.")


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    configure_console()
    if any(arg in {"-h", "--help"} for arg in args):
        print("Usage: python tools/demo.py [--live]")
        print("  (no flag)  offline scenarios only")
        print("  --live     add the optional bounded Gemini explanation check")
        return 0
    unknown = [arg for arg in args if arg != "--live"]
    if unknown:
        print("Unknown argument(s): " + ", ".join(unknown))
        print("Usage: python tools/demo.py [--live]")
        return 2

    run_offline_demo()
    if "--live" in args:
        run_live_demo()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
