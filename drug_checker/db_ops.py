import logging
import sqlite3
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

ALERT_TYPES = (
    "recalled",
    "suspended",
    "withdrawn",
    "cancelled",
    "warning",
)

DEFAULT_SEARCH_LIMIT = 10

# Minimum length before we also search inside names and ingredients.
# Shorter text (like "ve") only matches the START of a name.
MIN_WIDE_SEARCH_LENGTH = 3


# ----------------------------------------------------------------------
# Drug field definitions
# ----------------------------------------------------------------------

# Optional text fields of a drug record.
OPTIONAL_DRUG_FIELDS = (
    "generic_name",
    "manufacturer",
    "applicant",
    "strength",
    "dosage_form",
    "pack_size",
    "category",
    "marketing_category",
    "detail_url",
    "data_quality_note",
    "source",
)

# Optional date fields (YYYY-MM-DD).
# An invalid optional date is dropped, not fatal.
OPTIONAL_DRUG_DATE_FIELDS = (
    "approved_at",
    "expires_at",
)


# ----------------------------------------------------------------------
# Drug UPSERT statement
# ----------------------------------------------------------------------

# A re-import takes the newest snapshot of every field.
# The exception is manufacturer: a missing value must not erase
# a previously stored manufacturer name.

UPSERT_DRUG_SQL = """
INSERT INTO drugs (
    product_id,
    reg_number,
    reg_number_normalized,
    brand_name,
    name_normalized,
    generic_name,
    generic_normalized,
    manufacturer,
    applicant,
    strength,
    dosage_form,
    pack_size,
    category,
    marketing_category,
    registry_status,
    approved_at,
    expires_at,
    detail_url,
    data_quality_note,
    source,
    imported_at
)
VALUES (
    :product_id,
    :reg_number,
    :reg_number_normalized,
    :brand_name,
    :name_normalized,
    :generic_name,
    :generic_normalized,
    :manufacturer,
    :applicant,
    :strength,
    :dosage_form,
    :pack_size,
    :category,
    :marketing_category,
    :registry_status,
    :approved_at,
    :expires_at,
    :detail_url,
    :data_quality_note,
    :source,
    :imported_at
)
ON CONFLICT(product_id) DO UPDATE SET
    reg_number = excluded.reg_number,
    reg_number_normalized = excluded.reg_number_normalized,
    brand_name = excluded.brand_name,
    name_normalized = excluded.name_normalized,
    generic_name = excluded.generic_name,
    generic_normalized = excluded.generic_normalized,
    manufacturer = COALESCE(
        excluded.manufacturer,
        drugs.manufacturer
    ),
    applicant = excluded.applicant,
    strength = excluded.strength,
    dosage_form = excluded.dosage_form,
    pack_size = excluded.pack_size,
    category = excluded.category,
    marketing_category = excluded.marketing_category,
    registry_status = excluded.registry_status,
    approved_at = excluded.approved_at,
    expires_at = excluded.expires_at,
    detail_url = excluded.detail_url,
    data_quality_note = excluded.data_quality_note,
    source = excluded.source,
    imported_at = excluded.imported_at
"""


# ----------------------------------------------------------------------
# Small helper functions
# ----------------------------------------------------------------------

def utc_now() -> str:
    """Return the current UTC time as an ISO-formatted string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_name(name: str) -> str:
    """Normalize a drug name for consistent searching."""
    if not isinstance(name, str):
        raise TypeError("Drug name must be a string")

    name = name.lower()
    name = name.replace("-", " ")
    name = " ".join(name.split())

    if not name:
        raise ValueError("Drug name cannot be empty")

    return name


def normalize_reg_number(reg_number: str) -> str:
    """Normalize a registration number for consistent matching."""
    if not isinstance(reg_number, str):
        raise TypeError("Registration number must be a string")

    reg_number = reg_number.strip().upper()
    reg_number = reg_number.replace("-", "")
    reg_number = "".join(reg_number.split())

    if not reg_number:
        raise ValueError("Registration number cannot be empty")

    return reg_number


def _required_text(record: dict, field: str) -> str:
    """Return trimmed text for a required field, or raise an error."""
    if field not in record:
        raise ValueError(f"Missing required field: {field}")

    value = record[field]

    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")

    value = value.strip()

    if not value:
        raise ValueError(f"{field} cannot be empty")

    return value


def _optional_text(record: dict, field: str):
    """Return trimmed text, or None if the field is missing or blank."""
    value = record.get(field)

    if value is None:
        return None

    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string or None")

    value = value.strip()

    return value or None


def _validate_date(value: str, field: str) -> str:
    """Validate a date using the exact YYYY-MM-DD format."""
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")

    try:
        parsed_date = datetime.strptime(value, "%Y-%m-%d")

    except ValueError as error:
        raise ValueError(
            f"{field} must be in YYYY-MM-DD format"
        ) from error

    # Ensure the original value uses the exact required format.
    if parsed_date.strftime("%Y-%m-%d") != value:
        raise ValueError(
            f"{field} must be in YYYY-MM-DD format"
        )

    return value


def _optional_date_lenient(record: dict, field: str):
    """Return a valid date or None if the date is missing or invalid."""
    value = _optional_text(record, field)

    if value is None:
        return None

    try:
        return _validate_date(value, field)

    except ValueError:
        logger.warning(
            "Ignoring invalid %s: %r",
            field,
            value
        )
        return None


def _required_product_id(record: dict) -> int:
    """Validate and return the Greenbook product ID."""
    if "product_id" not in record:
        raise ValueError("Missing required field: product_id")

    value = record["product_id"]

    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 1
    ):
        raise TypeError(
            "product_id must be a positive whole number"
        )

    return value


def _escape_like(text: str) -> str:
    """Prevent user-typed % and _ from acting as SQL LIKE wildcards."""
    return (
        text.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
    )


# ----------------------------------------------------------------------
# Drugs: registry layer
# ----------------------------------------------------------------------

def _prepare_drug(drug: dict) -> dict:
    """
    Validate one drug record and prepare its database values.

    Required:
        product_id
        reg_number
        brand_name
        registry_status

    Invalid required fields raise TypeError or ValueError.
    Invalid optional dates are ignored.
    """

    if not isinstance(drug, dict):
        raise TypeError("Drug record must be a dictionary")

    product_id = _required_product_id(drug)
    reg_number = _required_text(drug, "reg_number")
    brand_name = _required_text(drug, "brand_name")
    registry_status = _required_text(drug, "registry_status")

    values = {
        "product_id": product_id,
        "reg_number": reg_number,
        "reg_number_normalized": normalize_reg_number(reg_number),
        "brand_name": brand_name,
        "name_normalized": normalize_name(brand_name),
        "registry_status": registry_status,
    }

    # Prepare optional text fields.
    for field in OPTIONAL_DRUG_FIELDS:
        values[field] = _optional_text(drug, field)

    # Prepare optional date fields.
    for field in OPTIONAL_DRUG_DATE_FIELDS:
        values[field] = _optional_date_lenient(drug, field)

    # An expiry date earlier than the approval date looks like a problem
    # in the source data. We store exactly what NAFDAC published and only
    # log a warning, because correcting the registry is not our decision.
    approved_at = values["approved_at"]
    expires_at = values["expires_at"]

    if (
        approved_at is not None
        and expires_at is not None
        and expires_at < approved_at
    ):
        logger.warning(
            "Product %s has an expiry date (%s) earlier than its "
            "approval date (%s). Keeping both as published.",
            product_id,
            expires_at,
            approved_at
        )

    # Normalize ingredient text for searching.
    values["generic_normalized"] = (
        normalize_name(values["generic_name"])
        if values["generic_name"]
        else None
    )

    return values


def _upsert_one(cursor, values: dict, imported_at: str) -> str:
    """
    Insert one drug or update an existing one.

    Returns:
        'added' or 'updated'
    """

    existing = cursor.execute(
        """
        SELECT 1
        FROM drugs
        WHERE product_id = ?
        """,
        (values["product_id"],)
    ).fetchone()

    cursor.execute(
        UPSERT_DRUG_SQL,
        {
            **values,
            "imported_at": imported_at,
        }
    )

    return "updated" if existing else "added"


def upsert_drug(conn, drug: dict) -> str:
    """
    Add a drug or update it if its product_id already exists.

    Returns:
        'added' or 'updated'

    Raises:
        TypeError / ValueError for invalid input.
        sqlite3.Error for database problems.
    """

    values = _prepare_drug(drug)

    try:
        with conn:
            result = _upsert_one(
                conn.cursor(),
                values,
                utc_now()
            )

    except sqlite3.Error:
        logger.exception(
            "Database error while saving drug %s",
            values["product_id"]
        )
        raise

    logger.info(
        "Drug %s: product %s (%s)",
        result,
        values["product_id"],
        values["reg_number"]
    )

    return result


def upsert_drugs(conn, records) -> dict:
    """
    Import multiple drug records in ONE transaction.

    Invalid records are skipped and logged.
    A database error rolls back the entire import.

    If the same product_id appears more than once in the records, the
    LAST one wins, and each extra appearance is counted as 'repeated'
    (not 'updated'). So the four counts always add up to the number of
    records you passed in.

    Returns:
        {
            'added': number,
            'updated': number,
            'skipped': number,
            'repeated': number
        }
    """

    counts = {
        "added": 0,
        "updated": 0,
        "skipped": 0,
        "repeated": 0,
    }

    imported_at = utc_now()
    seen_product_ids = set()

    try:
        with conn:
            cursor = conn.cursor()

            for position, record in enumerate(records, start=1):

                try:
                    values = _prepare_drug(record)

                except (TypeError, ValueError) as error:
                    counts["skipped"] += 1

                    logger.warning(
                        "Skipped record %s: %s",
                        position,
                        error
                    )

                    continue

                result = _upsert_one(
                    cursor,
                    values,
                    imported_at
                )

                if values["product_id"] in seen_product_ids:
                    counts["repeated"] += 1

                    logger.warning(
                        "Record %s repeats product_id %s; "
                        "the later record replaced the earlier one",
                        position,
                        values["product_id"]
                    )

                else:
                    seen_product_ids.add(values["product_id"])
                    counts[result] += 1

    except sqlite3.Error:
        logger.exception(
            "Import failed; all changes were rolled back"
        )
        raise

    logger.info(
        "Import finished: %s added, %s updated, %s skipped, %s repeated",
        counts["added"],
        counts["updated"],
        counts["skipped"],
        counts["repeated"]
    )

    return counts


# ----------------------------------------------------------------------
# Drug searching
# ----------------------------------------------------------------------

def find_by_name(
    conn,
    name: str,
    limit: int = DEFAULT_SEARCH_LIMIT
):
    """
    Find drugs by the name entered by the user.

    Every result has a match_rank:

        0: Exact brand-name match.
        1: Brand name starts with the search text.
        2: A word inside the brand name starts with the search text.
        3: Only the active ingredient contains the search text.

    Ranks 2 and 3 are only used for search text of 3+ characters.

    At most `limit` rows are returned. To find out whether MORE exist,
    ask for limit + 1 and drop the extra row.
    """

    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or limit < 1
    ):
        raise ValueError("limit must be a positive integer")

    exact = normalize_name(name)
    escaped = _escape_like(exact)

    params = {
        "exact": exact,
        "prefix": escaped + "%",
        "word": None,
        "ingredient": None,
        "limit": limit,
    }

    if len(exact) >= MIN_WIDE_SEARCH_LENGTH:
        params["word"] = "% " + escaped + "%"
        params["ingredient"] = "%" + escaped + "%"

    try:
        drugs = conn.execute(
            """
            SELECT *
            FROM (
                SELECT drugs.*,
                    CASE
                        WHEN name_normalized = :exact THEN 0
                        WHEN name_normalized LIKE :prefix
                            ESCAPE '\\' THEN 1
                        WHEN name_normalized LIKE :word
                            ESCAPE '\\' THEN 2
                        WHEN generic_normalized LIKE :ingredient
                            ESCAPE '\\' THEN 3
                    END AS match_rank
                FROM drugs
            )
            WHERE match_rank IS NOT NULL
            ORDER BY
                match_rank,
                name_normalized,
                product_id
            LIMIT :limit
            """,
            params
        ).fetchall()

    except sqlite3.Error:
        logger.exception(
            "Database error while searching for drug name"
        )
        raise

    logger.info(
        "Name search '%s': %s match(es)",
        exact,
        len(drugs)
    )

    return drugs


def find_by_reg_number(conn, reg_number: str):
    """
    Find every product with the supplied registration number.

    Returns a list because different Greenbook products can share
    the same registration number.
    """

    reg_number_normalized = normalize_reg_number(reg_number)

    try:
        drugs = conn.execute(
            """
            SELECT *
            FROM drugs
            WHERE reg_number_normalized = ?
            ORDER BY name_normalized, product_id
            """,
            (reg_number_normalized,)
        ).fetchall()

    except sqlite3.Error:
        logger.exception(
            "Database error while searching for registration number"
        )
        raise

    logger.info(
        "Registration number search '%s': %s match(es)",
        reg_number_normalized,
        len(drugs)
    )

    return drugs


def get_searchable_names(conn) -> list[str]:
    """Return names from the authoritative registry for parser disambiguation."""
    rows = conn.execute(
        "SELECT brand_name, generic_name FROM drugs ORDER BY product_id"
    ).fetchall()
    values = []
    for row in rows:
        values.extend(value for value in (row[0], row[1]) if isinstance(value, str) and value.strip())
    return values


def count_drugs(conn) -> int:
    """Return the total number of drug records."""

    try:
        return conn.execute(
            "SELECT COUNT(*) FROM drugs"
        ).fetchone()[0]

    except sqlite3.Error:
        logger.exception(
            "Database error while counting drugs"
        )
        raise


def view_all_drugs(conn):
    """
    Retrieve all drug records.

    FOR DEVELOPMENT AND TESTING ONLY. Never call this from the SMS
    or website handlers.
    """

    try:
        drugs = conn.execute(
            """
            SELECT *
            FROM drugs
            ORDER BY brand_name COLLATE NOCASE
            """
        ).fetchall()

    except sqlite3.Error:
        logger.exception(
            "Database error while retrieving all drug records"
        )
        raise

    logger.info(
        "Retrieved %s drug records",
        len(drugs)
    )

    return drugs


# ----------------------------------------------------------------------
# Alerts: regulatory noticeboard layer
# ----------------------------------------------------------------------

def add_alert(conn, alert: dict) -> int:
    """
    Record one regulatory alert.

    Required:
        alert_type
        product_name
        alert_date
        source_link

    Optional:
        reg_number
        reason
        resolved_date

    Returns:
        The newly created alert ID.
    """

    if not isinstance(alert, dict):
        raise TypeError("Alert record must be a dictionary")

    alert_type = _required_text(
        alert,
        "alert_type"
    ).lower()

    if alert_type not in ALERT_TYPES:
        raise ValueError(
            f"alert_type must be one of: {', '.join(ALERT_TYPES)}"
        )

    product_name = _required_text(
        alert,
        "product_name"
    )

    alert_date = _validate_date(
        _required_text(alert, "alert_date"),
        "alert_date"
    )

    source_link = _required_text(
        alert,
        "source_link"
    )

    reg_number = _optional_text(
        alert,
        "reg_number"
    )

    reason = _optional_text(
        alert,
        "reason"
    )

    resolved_date = _optional_text(
        alert,
        "resolved_date"
    )

    source_kind = alert.get("source_kind", "unknown")
    if source_kind not in {"regulatory", "synthetic", "unknown"}:
        raise ValueError("source_kind must be 'regulatory', 'synthetic', or 'unknown'")

    if resolved_date is not None:
        resolved_date = _validate_date(
            resolved_date,
            "resolved_date"
        )

        if resolved_date < alert_date:
            raise ValueError(
                "resolved_date cannot be earlier than alert_date"
            )

    reg_number_normalized = (
        normalize_reg_number(reg_number)
        if reg_number
        else None
    )

    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO alerts (
                    reg_number,
                    reg_number_normalized,
                    product_name,
                    product_name_normalized,
                    alert_type,
                    alert_date,
                    reason,
                    source_link,
                    resolved_date,
                    source_kind,
                    added_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reg_number,
                    reg_number_normalized,
                    product_name,
                    normalize_name(product_name),
                    alert_type,
                    alert_date,
                    reason,
                    source_link,
                    resolved_date,
                    source_kind,
                    utc_now()
                )
            )

            alert_id = cursor.lastrowid

    except sqlite3.Error:
        logger.exception(
            "Database error while saving alert for %s",
            product_name
        )
        raise

    logger.info(
        "Alert %s saved (%s: %s)",
        alert_id,
        alert_type,
        product_name
    )

    return alert_id


def find_alerts(
    conn,
    reg_number: str = None,
    name: str = None
):
    """
    Find alerts by registration number, product name, or both.

    Results are ordered newest first.

    An alert matched only by product name is weaker evidence
    than an alert matched by registration number.
    """

    if reg_number is None and name is None:
        raise ValueError(
            "Provide a reg_number, a name, or both"
        )

    # These SQL fragments are fixed strings, not user input.
    conditions = []
    params = []

    if reg_number is not None:
        conditions.append(
            "reg_number_normalized = ?"
        )

        params.append(
            normalize_reg_number(reg_number)
        )

    if name is not None:
        conditions.append(
            "product_name_normalized = ?"
        )

        params.append(
            normalize_name(name)
        )

    query = (
        "SELECT * FROM alerts WHERE "
        + " OR ".join(conditions)
        + " ORDER BY alert_date DESC, id DESC"
    )

    try:
        alerts = conn.execute(
            query,
            params
        ).fetchall()

    except sqlite3.Error:
        logger.exception(
            "Database error while searching alerts"
        )
        raise

    logger.info(
        "Alert search: %s result(s)",
        len(alerts)
    )

    return alerts


# ----------------------------------------------------------------------
# Data freshness
# ----------------------------------------------------------------------

def get_data_as_of(conn):
    """
    Return the date supplied by the latest trustworthy Greenbook fetch.

    Legacy imported_at values are ingestion timestamps, may reflect a bad
    host clock, and are not treated as the source's as-of date.
    """
    try:
        row = conn.execute(
            """SELECT source_fetched_at, completed_at, timestamp_anomaly
               FROM data_import_runs
               WHERE dataset = 'registry' AND status = 'success'
               ORDER BY id DESC LIMIT 1"""
        ).fetchone()
    except sqlite3.Error:
        # Existing databases remain usable before init_db adds the metadata
        # table. Their historical imported_at values are not trusted as source
        # freshness and therefore do not become data_as_of.
        logger.info("Registry import history is not available yet")
        return None

    if row is None or row[2] or not row[0]:
        return None
    parsed = _parse_aware_timestamp(row[0])
    completed = _parse_aware_timestamp(row[1])
    if (
        parsed is None
        or completed is None
        or completed > datetime.now(timezone.utc) + _CLOCK_SKEW_TOLERANCE
        or parsed > datetime.now(timezone.utc) + _CLOCK_SKEW_TOLERANCE
        or parsed > completed + _CLOCK_SKEW_TOLERANCE
    ):
        return None
    return parsed.date().isoformat()


_CLOCK_SKEW_TOLERANCE = timedelta(minutes=5)


def _parse_aware_timestamp(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def record_data_import(
    conn,
    dataset: str,
    source_name: str,
    source_fetched_at: str | None,
    row_count: int | None,
    status: str,
    *,
    completed_at: str | None = None,
    error_code: str | None = None,
    timestamp_anomaly: bool = False,
    anomaly_reason: str | None = None,
    imported_count: int | None = None,
    updated_count: int | None = None,
    skipped_count: int | None = None,
    rejected_count: int | None = None,
    duplicate_count: int | None = None,
) -> int:
    """Record one completed, traceable source import/check attempt."""
    if dataset not in {"registry", "alerts"}:
        raise ValueError("dataset must be 'registry' or 'alerts'")
    if status not in {"success", "error"}:
        raise ValueError("status must be 'success' or 'error'")
    if not isinstance(source_name, str) or not source_name.strip():
        raise ValueError("source_name cannot be empty")
    if row_count is not None and (
        isinstance(row_count, bool) or not isinstance(row_count, int) or row_count < 0
    ):
        raise ValueError("row_count must be a non-negative integer or None")
    if error_code is not None and not isinstance(error_code, str):
        raise TypeError("error_code must be a string or None")
    for field, value in (
        ("imported_count", imported_count),
        ("updated_count", updated_count),
        ("skipped_count", skipped_count),
        ("rejected_count", rejected_count),
        ("duplicate_count", duplicate_count),
    ):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise ValueError(f"{field} must be a non-negative integer or None")

    if completed_at is None:
        completed_at = utc_now()
    completed = _parse_aware_timestamp(completed_at)
    if completed is None:
        raise ValueError("completed_at must be an ISO timestamp with timezone")

    reasons = [anomaly_reason] if anomaly_reason else []
    anomalous = bool(timestamp_anomaly)
    if timestamp_anomaly and not anomaly_reason:
        reasons.append("source_timestamp_inconsistent")
    fetched = None
    if source_fetched_at is not None:
        fetched = _parse_aware_timestamp(source_fetched_at)
        if fetched is None:
            anomalous = True
            reasons.append("source_fetch_timestamp_unparseable_or_timezone_missing")
        elif fetched > completed + _CLOCK_SKEW_TOLERANCE:
            anomalous = True
            reasons.append("source_fetch_timestamp_after_ingestion")
    if completed > datetime.now(timezone.utc) + _CLOCK_SKEW_TOLERANCE:
        anomalous = True
        reasons.append("ingestion_timestamp_in_future")

    try:
        with conn:
            cursor = conn.execute(
                """INSERT INTO data_import_runs(
                    dataset, source_name, source_fetched_at, completed_at,
                    status, row_count, timestamp_anomaly, anomaly_reason,
                    error_code, imported_count, updated_count, skipped_count,
                    rejected_count, duplicate_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    dataset,
                    source_name.strip(),
                    source_fetched_at,
                    completed_at,
                    status,
                    row_count,
                    int(anomalous),
                    ";".join(dict.fromkeys(reasons)) or None,
                    error_code,
                    imported_count,
                    updated_count,
                    skipped_count,
                    rejected_count,
                    duplicate_count,
                ),
            )
            return cursor.lastrowid
    except sqlite3.Error:
        logger.exception("Could not record %s import metadata", dataset)
        raise


def _dataset_data_status(conn, dataset: str, stale_after_days: int, now=None) -> dict:
    if isinstance(stale_after_days, bool) or not isinstance(stale_after_days, int) or stale_after_days < 0:
        raise ValueError("stale_after_days must be a non-negative integer")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must include a timezone")
    now = now.astimezone(timezone.utc)
    try:
        row = conn.execute(
            """SELECT source_name, source_fetched_at, completed_at, status,
                      row_count, timestamp_anomaly, anomaly_reason, error_code
               FROM data_import_runs WHERE dataset = ? ORDER BY id DESC LIMIT 1""",
            (dataset,),
        ).fetchone()
    except sqlite3.Error:
        row = None  # additive migration has not yet been run

    result = {
        "status": "unknown",
        "source_name": None,
        "source_fetched_at": None,
        "completed_at": None,
        "row_count": None,
        "imported_count": None,
        "updated_count": None,
        "skipped_count": None,
        "rejected_count": None,
        "duplicate_count": None,
        "timestamp_anomaly": False,
        "anomaly_reason": None,
        "timestamp_trustworthy": False,
        "age_days": None,
        "error_code": None,
    }
    if row is None:
        if dataset == "registry":
            try:
                legacy = conn.execute("SELECT MAX(imported_at) FROM drugs").fetchone()[0]
                legacy_time = _parse_aware_timestamp(legacy)
                if legacy and (legacy_time is None or legacy_time > now + _CLOCK_SKEW_TOLERANCE):
                    result["timestamp_anomaly"] = True
                    result["anomaly_reason"] = "legacy_imported_at_untrusted_or_in_future"
            except sqlite3.Error:
                pass
        return result

    result.update({
        "source_name": row[0],
        "source_fetched_at": row[1],
        "completed_at": row[2],
        "row_count": row[4],
        "timestamp_anomaly": bool(row[5]),
        "anomaly_reason": row[6],
        "error_code": row[7],
    })
    try:
        counts = conn.execute(
            """SELECT imported_count, updated_count, skipped_count,
                      rejected_count, duplicate_count
               FROM data_import_runs WHERE dataset = ? ORDER BY id DESC LIMIT 1""",
            (dataset,),
        ).fetchone()
        if counts is not None:
            fields = (
                "imported_count", "updated_count", "skipped_count",
                "rejected_count", "duplicate_count",
            )
            if hasattr(counts, "keys"):
                result.update({field: counts[field] for field in fields})
            else:
                result.update(dict(zip(fields, counts)))
    except sqlite3.Error:
        # Older initialized databases do not have the additive count fields.
        pass
    if row[3] == "error":
        result["status"] = "error"
        return result

    completed = _parse_aware_timestamp(row[2])
    fetched = _parse_aware_timestamp(row[1]) if row[1] else None
    anomalous = bool(row[5]) or completed is None
    reasons = [row[6]] if row[6] else []
    if completed and completed > now + _CLOCK_SKEW_TOLERANCE:
        anomalous = True
        reasons.append("ingestion_timestamp_in_future")
    if row[1] and fetched is None:
        anomalous = True
        reasons.append("source_fetch_timestamp_unparseable_or_timezone_missing")
    if completed and fetched and fetched > completed + _CLOCK_SKEW_TOLERANCE:
        anomalous = True
        reasons.append("source_fetch_timestamp_after_ingestion")
    result["timestamp_anomaly"] = anomalous
    result["anomaly_reason"] = ";".join(dict.fromkeys(reasons)) or None
    freshness_time = fetched if dataset == "registry" else completed
    result["timestamp_trustworthy"] = not anomalous and freshness_time is not None
    if anomalous or row[4] is None or freshness_time is None:
        return result

    age = now - freshness_time
    result["age_days"] = max(age.days, 0)
    result["status"] = "stale" if age > timedelta(days=stale_after_days) else "loaded"
    return result


def get_registry_data_status(conn, stale_after_days: int = 30, now=None) -> dict:
    """Return freshness and provenance for the latest Greenbook import."""
    return _dataset_data_status(conn, "registry", stale_after_days, now)


def get_alert_data_status(conn, stale_after_days: int = 30, now=None) -> dict:
    """Return freshness and provenance for the latest alert source check."""
    return _dataset_data_status(conn, "alerts", stale_after_days, now)
