"""Explicitly seed a clearly synthetic alert for local demonstrations only."""

from __future__ import annotations

import logging
import sys

from .config import DB_PATH
from .database import create_connection
from .db_ops import add_alert

logger = logging.getLogger(__name__)

DEMO_SOURCE_LINK = "https://example.invalid/demo/synthetic-alert-v1"
DEMO_ALERT = {
    "reg_number": "ZZ-0001",
    "product_name": "SYNTHETIC DEMO PRODUCT",
    "alert_type": "warning",
    "alert_date": "2026-01-01",
    "reason": (
        "SYNTHETIC — DEMONSTRATION ONLY; fictional fixture, "
        "not an actual NAFDAC notice."
    ),
    "source_link": DEMO_SOURCE_LINK,
    "source_kind": "synthetic",
}


def main() -> int:
    conn = create_connection(DB_PATH)
    if conn is None:
        return 1
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(alerts)")}
        if "source_kind" not in columns:
            logger.error("Alert source-kind migration is missing; run drug_checker.init_db first")
            return 1
        existing = conn.execute(
            "SELECT id FROM alerts WHERE source_link=? AND source_kind='synthetic' LIMIT 1",
            (DEMO_SOURCE_LINK,),
        ).fetchone()
        if existing:
            print("Synthetic demonstration alert already exists; no changes made.")
            return 0
        add_alert(conn, DEMO_ALERT)
        print("Seeded 1 SYNTHETIC — DEMONSTRATION ONLY alert (not a real NAFDAC notice).")
        return 0
    except Exception:
        logger.exception("Could not seed synthetic demonstration alert")
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
