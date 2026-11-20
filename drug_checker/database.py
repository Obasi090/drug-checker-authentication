import sqlite3
from pathlib import Path
import logging 

logger = logging.getLogger(__name__)


def create_connection(db_path: Path):
    try:
        conn = sqlite3.connect(db_path, timeout=5)
        conn.row_factory = sqlite3.Row

        conn.execute("PRAGMA foreign_keys = ON;")

        logger.info("Connection to %s successful", db_path)
        
        #print(f'Connection to {db_path} successful')
        return conn
        
    except sqlite3.Error:
        logger.exception("Failed to establish database connection")
        return None
