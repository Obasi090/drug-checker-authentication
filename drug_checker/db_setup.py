import logging
import sqlite3

logger = logging.getLogger(__name__)


def create_drugs_table(conn):
    try:
        cursor = conn.cursor()

        # product_id is the Greenbook's own ID for a record. It is the key
        # because registration numbers are NOT unique in the Greenbook:
        # different products can share one.
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS drugs(
            product_id INTEGER PRIMARY KEY,
            reg_number TEXT NOT NULL,
            reg_number_normalized TEXT NOT NULL,
            brand_name TEXT NOT NULL,
            name_normalized TEXT NOT NULL,
            generic_name TEXT,
            generic_normalized TEXT,
            manufacturer TEXT,
            applicant TEXT,
            strength TEXT,
            dosage_form TEXT,
            pack_size TEXT,
            category TEXT,
            marketing_category TEXT,
            registry_status TEXT NOT NULL,
            approved_at TEXT,
            expires_at TEXT,
            detail_url TEXT,
            data_quality_note TEXT,
            source TEXT,
            imported_at TEXT NOT NULL
        )
        ''')

        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_drugs_name_normalized
        ON drugs (name_normalized)
        ''')

        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_drugs_reg_number_normalized
        ON drugs (reg_number_normalized)
        ''')

        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_drugs_generic_normalized
        ON drugs (generic_normalized)
        ''')

        conn.commit()

        logger.info("Table 'drugs' and its indexes are ready")
        return True

    except sqlite3.Error:
        conn.rollback()
        logger.exception("Failed to create 'drugs' table or indexes")
        return False


def create_alerts_table(conn):
    try:
        cursor = conn.cursor()

        # reg_number is optional because some public alerts name a product
        # without a registration number. Those alerts are found by
        # product_name_normalized instead.
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts(
            id INTEGER PRIMARY KEY,
            reg_number TEXT,
            reg_number_normalized TEXT,
            product_name TEXT NOT NULL,
            product_name_normalized TEXT NOT NULL,
            alert_type TEXT NOT NULL CHECK(alert_type IN (
                'recalled', 'suspended', 'withdrawn', 'cancelled', 'warning'
            )),
            alert_date TEXT NOT NULL,
            reason TEXT,
            source_link TEXT NOT NULL,
            resolved_date TEXT,
            source_kind TEXT NOT NULL DEFAULT 'unknown'
                CHECK(source_kind IN ('regulatory', 'synthetic', 'unknown')),
            added_at TEXT NOT NULL
        )
        ''')

        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(alerts)")
        }
        if "source_kind" not in existing_columns:
            conn.execute(
                "ALTER TABLE alerts ADD COLUMN source_kind TEXT NOT NULL "
                "DEFAULT 'unknown' CHECK(source_kind IN ('regulatory', 'synthetic', 'unknown'))"
            )
        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_alerts_reg_number_normalized
        ON alerts (reg_number_normalized)
        ''')

        cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_alerts_product_name_normalized
        ON alerts (product_name_normalized)
        ''')

        conn.commit()

        logger.info("Table 'alerts' and its indexes are ready")
        return True

    except sqlite3.Error:
        conn.rollback()
        logger.exception("Failed to create 'alerts' table or indexes")
        return False


def create_data_import_runs_table(conn):
    """Create additive, auditable metadata for registry/alert data checks."""
    try:
        conn.execute('''
        CREATE TABLE IF NOT EXISTS data_import_runs(
            id INTEGER PRIMARY KEY,
            dataset TEXT NOT NULL CHECK(dataset IN ('registry', 'alerts')),
            source_name TEXT NOT NULL,
            source_fetched_at TEXT,
            completed_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('success', 'error')),
            row_count INTEGER CHECK(row_count IS NULL OR row_count >= 0),
            timestamp_anomaly INTEGER NOT NULL DEFAULT 0
                CHECK(timestamp_anomaly IN (0, 1)),
            anomaly_reason TEXT,
            error_code TEXT
        )
        ''')
        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(data_import_runs)")
        }
        for column in (
            "imported_count", "updated_count", "skipped_count",
            "rejected_count", "duplicate_count",
        ):
            if column not in existing_columns:
                conn.execute(f"ALTER TABLE data_import_runs ADD COLUMN {column} INTEGER")
        conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_data_import_runs_dataset_completed
        ON data_import_runs (dataset, completed_at DESC, id DESC)
        ''')
        conn.commit()
        logger.info("Table 'data_import_runs' is ready")
        return True
    except sqlite3.Error:
        conn.rollback()
        logger.exception("Failed to create 'data_import_runs' table")
        return False


def create_all_tables(conn):
    """Create every table. Returns True only if all succeeded."""
    return (
        create_drugs_table(conn)
        and create_alerts_table(conn)
        and create_data_import_runs_table(conn)
    )
