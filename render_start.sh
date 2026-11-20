#!/usr/bin/env bash
set -eu

PROJECT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export DRUG_CHECKER_DB_PATH="${DRUG_CHECKER_DB_PATH:-/var/data/drugs.db}"
export DRUG_CHECKER_LOG_PATH="${DRUG_CHECKER_LOG_PATH:-/var/data/drug_db.log}"

mkdir -p "$(dirname -- "$DRUG_CHECKER_DB_PATH")" "$(dirname -- "$DRUG_CHECKER_LOG_PATH")"

# Seed only a new persistent-disk path. Never replace an existing database.
if [ ! -f "$DRUG_CHECKER_DB_PATH" ]; then
  if [ ! -f "$PROJECT_DIR/data/deployment_seed.sqlite3" ]; then
    echo "Deployment seed database is missing; refusing to create an empty database." >&2
    exit 1
  fi
  cp "$PROJECT_DIR/data/deployment_seed.sqlite3" "$DRUG_CHECKER_DB_PATH"
fi

cd "$PROJECT_DIR"
python -m drug_checker.init_db
exec gunicorn --bind "0.0.0.0:${PORT:-10000}" --workers 1 --timeout 120 'drug_checker.api:create_app()'
