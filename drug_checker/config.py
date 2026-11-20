import os
from pathlib import Path

# The package folder (the folder that contains this file)
BASE_DIR = Path(__file__).resolve().parent

# The project root (one level up) and its data folder
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

def _configured_path(variable: str, default: Path) -> Path:
    value = os.environ.get(variable, "").strip()
    return Path(value).expanduser().resolve() if value else default.resolve()


DB_PATH = _configured_path("DRUG_CHECKER_DB_PATH", BASE_DIR / "drugs.db")
LOG_PATH = _configured_path("DRUG_CHECKER_LOG_PATH", BASE_DIR / "drug_db.log")

# Used when you run the importer without giving it a file
DEFAULT_GREENBOOK_FILE = DATA_DIR / "greenbook_sample.json"
