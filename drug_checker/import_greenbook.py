"""Import NAFDAC Greenbook records (an Apify JSON export) into the database.

Run from the project root (the folder that CONTAINS your package):

    python -m your_package_name.import_greenbook
    python -m your_package_name.import_greenbook data/greenbook_sample.json

With no file given, it reads data/greenbook_sample.json.
It is safe to run again: existing products are updated, not duplicated.
"""
import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

from .config import DB_PATH, DEFAULT_GREENBOOK_FILE, LOG_PATH
from .database import create_connection
from .db_ops import (
    _prepare_drug,
    count_drugs,
    record_data_import,
    upsert_drugs,
)
from .logging_config import setup_logging

logger = logging.getLogger(__name__)

SOURCE_NAME = "NAFDAC Greenbook"
DEMO_SOURCE_NAME = "NAFDAC Greenbook sample/demo dataset"


def load_records(path: Path) -> list:
    """Read the JSON file and return its list of records."""
    # utf-8-sig also copes with a hidden byte-order mark at the start
    with open(path, encoding="utf-8-sig") as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(
            "Expected a JSON list of records (a dataset export from Apify)"
        )

    return data


def _name_of(value):
    """Greenbook gives applicant/manufacturer as {id, name, ...}."""
    return value.get("name") if isinstance(value, dict) else None


def flatten_record(raw, *, source_name=SOURCE_NAME):
    """Turn one Greenbook record into the flat dictionary our database uses.

    Only the fields we need are copied. Free-text fields we do not need
    (composition, description, SmPC links) are left out on purpose.
    A record that is not a dictionary is passed on unchanged, so the
    importer can skip and log it.
    """
    if not isinstance(raw, dict):
        return raw

    ingredients = raw.get("activeIngredients")
    if isinstance(ingredients, list):
        generic_name = "; ".join(
            str(item).strip() for item in ingredients if item and str(item).strip()
        ) or None
    else:
        generic_name = None

    fetched = raw.get("fetchedAt")
    quality_note = raw.get("dataQualityNote")
    is_synthetic_demo = (
        isinstance(quality_note, str)
        and quality_note.strip().casefold().startswith("demo/sample only")
    )
    source = (
        "DEMO/SAMPLE only — synthetic educational entry; not a NAFDAC record"
        if is_synthetic_demo
        else source_name
    )
    if not is_synthetic_demo and isinstance(fetched, str) and len(fetched) >= 10:
        source = f"{source_name}, fetched {fetched[:10]}"

    return {
        "product_id": raw.get("productId"),
        "reg_number": raw.get("registrationNumber"),
        "brand_name": raw.get("productName"),
        "registry_status": raw.get("status"),
        "generic_name": generic_name,
        "manufacturer": _name_of(raw.get("manufacturer")),
        "applicant": _name_of(raw.get("applicant")),
        "strength": raw.get("strength"),
        "dosage_form": raw.get("dosageForm"),
        "pack_size": raw.get("packSize"),
        "category": raw.get("category"),
        "marketing_category": raw.get("marketingCategory"),
        "approved_at": raw.get("approvedAt"),
        "expires_at": raw.get("expiresAt"),
        "detail_url": raw.get("detailUrl"),
        "data_quality_note": raw.get("dataQualityNote"),
        "source": source,
    }


def _source_fetch_time(records):
    """Return the sole source fetch timestamp, flagging mixed snapshots."""
    source_records = [raw for raw in records if isinstance(raw, dict)]
    values = [raw.get("fetchedAt") for raw in source_records]
    present = [value for value in values if value is not None]
    if not present:
        return None, False
    if len(present) != len(values) or any(not isinstance(value, str) for value in values):
        return None, True
    distinct = set(values)
    if len(distinct) == 1:
        return next(iter(distinct)), False
    if len(distinct) > 1:
        return None, True
    return None, False


def analyze_records(records, conn):
    """Summarize an import without changing the database."""
    valid = []
    rejected = 0
    seen = set()
    repeated = 0

    for raw in records:
        try:
            values = _prepare_drug(flatten_record(raw))
        except (TypeError, ValueError):
            rejected += 1
            continue
        product_id = values["product_id"]
        if product_id in seen:
            repeated += 1
        else:
            seen.add(product_id)
            valid.append(product_id)

    existing = {
        row[0]
        for row in conn.execute("SELECT product_id FROM drugs").fetchall()
    }
    updates = sum(product_id in existing for product_id in valid)
    inserts = len(valid) - updates
    return {
        "total": len(records),
        "valid": len(records) - rejected,
        "rejected": rejected,
        "duplicates": repeated,
        "would_insert": inserts,
        "would_update": updates,
        "would_skip": rejected,
    }


def _print_dry_run(path, source_fetched_at, counts):
    print(f"Dry run: {path}")
    print(f"Source fetch date: {source_fetched_at or 'unknown'}")
    print(f"Total: {counts['total']}; valid: {counts['valid']}; rejected: {counts['rejected']}")
    print(f"Duplicates: {counts['duplicates']}; would insert: {counts['would_insert']}; "
          f"would update: {counts['would_update']}; would skip: {counts['would_skip']}")


def _record_failed_attempt(
    source_fetched_at=None, row_count=None, anomaly=False, source_name=SOURCE_NAME
):
    """Best-effort failure history when the initialized database is available."""
    conn = create_connection(DB_PATH)
    if conn is None:
        return
    try:
        record_data_import(
            conn,
            "registry",
            source_name,
            source_fetched_at,
            row_count,
            "error",
            error_code="import_failed",
            timestamp_anomaly=anomaly,
            anomaly_reason="mixed_source_fetch_timestamps" if anomaly else None,
        )
    except sqlite3.Error:
        logger.error("Could not record failed Greenbook import metadata")
    finally:
        conn.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Import NAFDAC Greenbook records into the drugs table."
    )
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=DEFAULT_GREENBOOK_FILE,
        help="JSON file to import (default: %(default)s)",
    )
    parser.add_argument(
        "--demo-sample",
        action="store_true",
        help="Mark this import explicitly as a limited demonstration sample",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and summarize the source without changing database rows or history",
    )
    args = parser.parse_args(argv)
    if args.file.resolve() == DEFAULT_GREENBOOK_FILE.resolve():
        args.demo_sample = True
    source_name = DEMO_SOURCE_NAME if args.demo_sample else SOURCE_NAME

    setup_logging(LOG_PATH)

    try:
        raw_records = load_records(args.file)
    except OSError as error:
        logger.error("Could not read %s: %s", args.file, error)
        if not args.dry_run:
            _record_failed_attempt(source_name=source_name)
        return 1
    except ValueError as error:  # includes invalid JSON
        logger.error("Could not understand %s: %s", args.file, error)
        if not args.dry_run:
            _record_failed_attempt(source_name=source_name)
        return 1

    logger.info("Read %s records from %s", len(raw_records), args.file)

    conn = create_connection(DB_PATH)
    if conn is None:
        return 1

    try:
        conn.execute("SELECT 1 FROM data_import_runs LIMIT 1")
    except sqlite3.Error:
        logger.error(
            "Import history is not initialized. Run "
            "python -m drug_checker.init_db before importing; no rows were changed."
        )
        conn.close()
        return 1

    source_fetched_at, mixed_snapshots = _source_fetch_time(raw_records)
    try:
        analysis = analyze_records(raw_records, conn)
    except sqlite3.Error:
        logger.error("Could not inspect existing products; import was not run")
        conn.close()
        return 1

    if args.dry_run:
        _print_dry_run(args.file, source_fetched_at, analysis)
        conn.close()
        return 0

    if analysis["rejected"]:
        try:
            record_data_import(
                conn,
                "registry",
                source_name,
                source_fetched_at,
                len(raw_records),
                "error",
                error_code="invalid_source_records",
                skipped_count=analysis["rejected"],
                rejected_count=analysis["rejected"],
                duplicate_count=analysis["duplicates"],
                timestamp_anomaly=mixed_snapshots,
                anomaly_reason="mixed_source_fetch_timestamps" if mixed_snapshots else None,
            )
        finally:
            conn.close()
        logger.error(
            "Import stopped before changing products: %s source record(s) were invalid",
            analysis["rejected"],
        )
        return 1

    try:
        counts = upsert_drugs(
            conn,
            (flatten_record(r, source_name=source_name) for r in raw_records),
        )
        total = count_drugs(conn)
    except sqlite3.Error:
        logger.error(
            "Import failed. Ensure the database is initialized with "
            "python -m drug_checker.init_db; do not delete the existing database."
        )
        try:
            record_data_import(
                conn,
                "registry",
                source_name,
                source_fetched_at,
                len(raw_records),
                "error",
                error_code="database_import_failed",
                skipped_count=analysis["rejected"],
                rejected_count=analysis["rejected"],
                duplicate_count=analysis["duplicates"],
                timestamp_anomaly=mixed_snapshots,
                anomaly_reason="mixed_source_fetch_timestamps" if mixed_snapshots else None,
            )
        except sqlite3.Error:
            logger.error("Could not record failed Greenbook import metadata")
        conn.close()
        return 1

    try:
        record_data_import(
            conn,
            "registry",
            source_name,
            source_fetched_at,
            len(raw_records),
            "success",
            imported_count=counts["added"],
            updated_count=counts["updated"],
            skipped_count=counts["skipped"],
            rejected_count=0,
            duplicate_count=counts["repeated"],
            timestamp_anomaly=mixed_snapshots,
            anomaly_reason="mixed_source_fetch_timestamps" if mixed_snapshots else None,
        )
    except sqlite3.Error:
        logger.error("Greenbook rows were imported, but import metadata was not recorded")
        return 1
    finally:
        conn.close()

    message = (
        f"Imported {args.file.name}: {counts['added']} added, "
        f"{counts['updated']} updated, {counts['skipped']} skipped"
    )
    if counts["repeated"]:
        message += f", {counts['repeated']} repeated within the file"
    message += f". The database now holds {total} products."

    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
