"""Create the database file and its tables.

Run from the folder that CONTAINS your package:
    python -m your_package_name.init_db
"""
import logging
import sys

from .config import DB_PATH, LOG_PATH
from .database import create_connection
from .db_setup import create_all_tables
from .logging_config import setup_logging

logger = logging.getLogger(__name__)


def main() -> int:
    setup_logging(LOG_PATH)
    logger.info("Database will be stored at: %s", DB_PATH)

    conn = create_connection(DB_PATH)
    if conn is None:
        logger.error("Database setup failed: could not connect")
        return 1

    try:
        if not create_all_tables(conn):
            logger.error("Database setup failed: could not create tables")
            return 1

        logger.info("Database setup completed")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
