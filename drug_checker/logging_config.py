import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_configured = False


def setup_logging(log_file: Path, level: int = logging.INFO) -> None:
    """Configure logging for the whole program.

    Call this ONCE, from the entry point (init_db.py now, the web/SMS
    app later). Library modules should only do:
        logger = logging.getLogger(__name__)
    """
    global _configured
    if _configured:
        return

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s]: %(message)s"
    )

    # File: keeps history, rotates at ~1 MB so it can't grow forever
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    # Console: so you see messages while testing
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    _configured = True
