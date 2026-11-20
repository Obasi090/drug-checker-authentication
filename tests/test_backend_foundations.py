from __future__ import annotations

import sqlite3
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from drug_checker.db_ops import (
    add_alert,
    get_alert_data_status,
    get_data_as_of,
    get_registry_data_status,
    record_data_import,
    upsert_drug,
)
from drug_checker.db_setup import create_all_tables, create_alerts_table, create_drugs_table
from drug_checker.engine import check_name, check_reg_number
from drug_checker.import_greenbook import _source_fetch_time, flatten_record
from drug_checker.sms_replies import build_sms


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    assert create_all_tables(connection)
    yield connection
    connection.close()


def _drug(conn, **overrides):
    values = {
        "product_id": 101,
        "reg_number": "A4-1234",
        "brand_name": "Example Medicine 10 mg",
        "registry_status": "Active",
        "manufacturer": "Example Pharma",
    }
    values.update(overrides)
    return upsert_drug(conn, values)


def _record_success(conn, dataset, *, completed_at=None, fetched_at=None, row_count=1):
    now = datetime.now(timezone.utc)
    completed_at = completed_at or now.isoformat()
    fetched_at = fetched_at or (now - timedelta(days=1)).isoformat()
    return record_data_import(
        conn,
        dataset,
        "Test source",
        fetched_at,
        row_count,
        "success",
        completed_at=completed_at,
    )


def test_additive_schema_is_compatible_with_existing_tables():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    assert create_drugs_table(connection)
    assert create_alerts_table(connection)
    upsert_drug(connection, {
        "product_id": 7,
        "reg_number": "B4-7777",
        "brand_name": "Existing Product",
        "registry_status": "Active",
        "imported_at": "2020-01-01T00:00:00+00:00",
    })
    connection.execute(
        "UPDATE drugs SET imported_at=? WHERE product_id=7",
        ("2020-01-01T00:00:00+00:00",),
    )

    assert create_all_tables(connection)
    assert connection.execute("SELECT brand_name FROM drugs WHERE product_id=7").fetchone()[0] == "Existing Product"
    assert connection.execute("SELECT COUNT(*) FROM data_import_runs").fetchone()[0] == 0
    connection.close()


def test_new_schema_creates_import_history_table(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(data_import_runs)")}
    assert {
        "dataset", "source_name", "source_fetched_at", "completed_at",
        "status", "row_count", "timestamp_anomaly", "anomaly_reason", "error_code",
    } <= columns


def test_success_and_failed_import_metadata_are_recorded(conn):
    fetched = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    success_id = record_data_import(
        conn, "registry", "NAFDAC Greenbook", fetched, 0, "success"
    )
    failure_id = record_data_import(
        conn, "alerts", "NAFDAC alert source", None, None, "error",
        error_code="source_unavailable",
    )
    success = conn.execute("SELECT * FROM data_import_runs WHERE id=?", (success_id,)).fetchone()
    failure = conn.execute("SELECT * FROM data_import_runs WHERE id=?", (failure_id,)).fetchone()
    assert success["status"] == "success" and success["row_count"] == 0
    assert success["source_fetched_at"] == fetched
    assert failure["status"] == "error" and failure["row_count"] is None
    assert failure["error_code"] == "source_unavailable"


def test_greenbook_importer_records_source_and_ingestion_separately(tmp_path, monkeypatch):
    from drug_checker import import_greenbook

    db_path = tmp_path / "temporary.sqlite"
    connection = sqlite3.connect(db_path)
    assert create_all_tables(connection)
    connection.close()
    source_file = tmp_path / "greenbook.json"
    fetched = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    source_file.write_text(json.dumps([{
        "productId": 55,
        "registrationNumber": "C4-5555",
        "productName": "Temporary Test Product",
        "status": "Active",
        "fetchedAt": fetched,
    }]), encoding="utf-8")
    monkeypatch.setattr(import_greenbook, "DB_PATH", db_path)
    monkeypatch.setattr(import_greenbook, "LOG_PATH", tmp_path / "import.log")

    assert import_greenbook.main(["--demo-sample", str(source_file)]) == 0
    assert import_greenbook.main([str(tmp_path / "missing.json")]) == 1
    connection = sqlite3.connect(db_path)
    runs = connection.execute(
        "SELECT source_fetched_at, completed_at, status, row_count, source_name "
        "FROM data_import_runs WHERE dataset='registry' ORDER BY id"
    ).fetchall()
    record = connection.execute(
        "SELECT imported_at, source FROM drugs WHERE product_id=55"
    ).fetchone()
    import_counts = connection.execute(
        "SELECT imported_count, updated_count, skipped_count, rejected_count, duplicate_count "
        "FROM data_import_runs WHERE dataset='registry' AND status='success'"
    ).fetchone()
    connection.close()

    assert runs[0][0] == fetched
    assert runs[0][1] != fetched
    assert runs[0][2:4] == ("success", 1)
    assert runs[0][4] == "NAFDAC Greenbook sample/demo dataset"
    assert runs[1][2:4] == ("error", None)
    assert record[0] == runs[0][1]
    assert "fetched " + fetched[:10] in record[1]
    assert "sample/demo" in record[1]
    assert import_counts == (1, 0, 0, 0, 0)


def test_mixed_greenbook_fetch_timestamps_are_flagged():
    fetched, anomaly = _source_fetch_time([
        {"fetchedAt": "2026-01-01T00:00:00Z"},
        {"fetchedAt": "2026-01-02T00:00:00Z"},
    ])
    assert fetched is None
    assert anomaly is True
    assert _source_fetch_time([{"fetchedAt": {"unexpected": "object"}}]) == (None, True)


def test_missing_fetch_time_in_a_partially_timestamped_file_is_flagged():
    fetched = "2026-11-19T15:27:47.143Z"
    assert _source_fetch_time([
        {"fetchedAt": fetched},
        {"fetchedAt": None},
    ]) == (None, True)


def test_synthetic_demo_record_keeps_distinct_source_provenance():
    flattened = flatten_record({
        "productId": 99000021,
        "registrationNumber": "DEMO-000021",
        "productName": "DEMO/SAMPLE — Paracetamol",
        "status": "DEMO/SAMPLE ONLY — NOT A REGULATORY STATUS",
        "dataQualityNote": "DEMO/SAMPLE ONLY — synthetic fixture, not a NAFDAC record.",
        "fetchedAt": None,
    }, source_name="NAFDAC Greenbook sample/demo dataset")
    assert flattened["source"].startswith("DEMO/SAMPLE only")


def test_future_ingestion_timestamp_is_anomalous_and_not_freshness(conn):
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    record_data_import(
        conn, "alerts", "Test alert source", None, 0, "success",
        completed_at=future,
    )
    status = get_alert_data_status(conn)
    assert status["status"] == "unknown"
    assert status["timestamp_anomaly"] is True
    assert status["timestamp_trustworthy"] is False


def test_future_source_fetch_timestamp_is_anomalous(conn):
    now = datetime.now(timezone.utc)
    fetched = (now + timedelta(days=1)).isoformat()
    record_data_import(
        conn, "alerts", "Test alert source", fetched, 0, "success",
        completed_at=now.isoformat(),
    )
    status = get_alert_data_status(conn, now=now)
    assert status["status"] == "unknown"
    assert status["timestamp_anomaly"] is True


def test_alert_dataset_status_unknown_without_successful_check(conn):
    assert conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0] == 0
    assert get_alert_data_status(conn)["status"] == "unknown"


def test_alert_dataset_status_loaded_for_successful_zero_row_check(conn):
    now = datetime.now(timezone.utc)
    _record_success(conn, "alerts", completed_at=now.isoformat(), row_count=0)
    status = get_alert_data_status(conn, now=now)
    assert status["status"] == "loaded"
    assert status["row_count"] == 0
    assert status["timestamp_trustworthy"] is True


def test_alert_dataset_status_stale_from_trustworthy_completion(conn):
    now = datetime.now(timezone.utc)
    completed = now - timedelta(days=45)
    fetched = (completed - timedelta(days=1)).isoformat()
    _record_success(
        conn, "alerts", completed_at=completed.isoformat(), fetched_at=fetched, row_count=3
    )
    status = get_alert_data_status(conn, stale_after_days=30, now=now)
    assert status["status"] == "stale"
    assert status["age_days"] == 45


def test_latest_failed_alert_check_reports_error(conn):
    now = datetime.now(timezone.utc)
    _record_success(conn, "alerts", completed_at=now.isoformat())
    record_data_import(
        conn, "alerts", "Test alert source", None, None, "error",
        error_code="source_unavailable",
    )
    assert get_alert_data_status(conn)["status"] == "error"


def test_registry_as_of_uses_source_fetch_date_not_ingestion_date(conn):
    now = datetime.now(timezone.utc)
    fetched = (now - timedelta(days=3)).isoformat()
    _record_success(conn, "registry", completed_at=now.isoformat(), fetched_at=fetched)
    assert get_data_as_of(conn) == (now - timedelta(days=3)).date().isoformat()
    assert get_registry_data_status(conn, now=now)["status"] == "loaded"


def test_registry_without_source_fetch_time_does_not_claim_freshness(conn):
    now = datetime.now(timezone.utc)
    record_data_import(
        conn, "registry", "Test source", None, 12, "success",
        completed_at=now.isoformat(),
    )
    status = get_registry_data_status(conn, now=now)
    assert status["status"] == "unknown"
    assert status["timestamp_trustworthy"] is False
    assert get_data_as_of(conn) is None


def test_legacy_future_imported_at_is_flagged_not_used_as_freshness(conn):
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    _drug(conn)
    conn.execute("UPDATE drugs SET imported_at=? WHERE product_id=101", (future,))
    status = get_registry_data_status(conn)
    assert status["status"] == "unknown"
    assert status["timestamp_anomaly"] is True
    assert get_data_as_of(conn) is None


def test_name_and_registration_lookups_and_alert_strength_regression(conn):
    _drug(conn)
    reg_alert = add_alert(conn, {
        "reg_number": "A4-1234",
        "product_name": "Example Medicine 10 mg",
        "alert_type": "warning",
        "alert_date": "2026-01-01",
        "source_link": "https://example.test/alert/1",
    })
    name_alert = add_alert(conn, {
        "product_name": "Example Medicine 10 mg",
        "alert_type": "recalled",
        "alert_date": "2026-01-02",
        "source_link": "https://example.test/alert/2",
    })

    by_reg = check_reg_number(conn, "A4-1234")
    by_name = check_name(conn, "Example Medicine 10 mg")
    assert by_reg["matches"][0]["product_id"] == 101
    assert {a["id"] for a in by_reg["alerts"]} == {reg_alert, name_alert}
    assert {a["matched_by"] for a in by_reg["alerts"]} == {"reg_number", "name"}
    assert by_name["matches"][0]["product_id"] == 101


def test_sms_does_not_claim_no_alert_when_alert_state_unknown():
    reply = build_sms({
        "status": "found",
        "query_type": "reg_number",
        "query": "A4-1234",
        "matches": [{
            "brand_name": "Example Medicine",
            "reg_number": "A4-1234",
            "registry_status": "Active",
            "manufacturer": None,
        }],
        "alerts": [],
        "data_as_of": None,
        "alert_data_status": {"status": "unknown"},
    })
    assert "unknown" in reply.casefold()
    assert "no alert on record" not in reply.casefold()


def test_metadata_validation_rejects_negative_row_count(conn):
    with pytest.raises(ValueError):
        record_data_import(conn, "alerts", "source", None, -1, "success")



def test_greenbook_dry_run_reports_counts_without_database_changes(tmp_path, monkeypatch, capsys):
    from drug_checker import import_greenbook

    db_path = tmp_path / "dry-run.sqlite"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    assert create_all_tables(conn)
    _drug(conn, product_id=10, reg_number="A4-0010", brand_name="Existing Fixture")
    conn.close()
    source = tmp_path / "fixture.json"
    source.write_text(json.dumps([
        {"productId": 10, "registrationNumber": "A4-0010", "productName": "Existing Fixture", "status": "Active"},
        {"productId": 11, "registrationNumber": "A4-0011", "productName": "New Fixture", "status": "Active"},
        {"productId": 11, "registrationNumber": "A4-0011", "productName": "Duplicate Fixture", "status": "Active"},
        {"productId": "invalid", "registrationNumber": "A4-0012", "productName": "Rejected Fixture", "status": "Active"},
    ]), encoding="utf-8")
    monkeypatch.setattr(import_greenbook, "DB_PATH", db_path)
    monkeypatch.setattr(import_greenbook, "LOG_PATH", tmp_path / "dry-run.log")

    assert import_greenbook.main(["--dry-run", str(source)]) == 0
    output = capsys.readouterr().out
    assert "Total: 4; valid: 3; rejected: 1" in output
    assert "Duplicates: 1; would insert: 1; would update: 1; would skip: 1" in output
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM drugs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM data_import_runs").fetchone()[0] == 0
    conn.close()


def test_invalid_greenbook_import_does_not_partially_upsert(tmp_path, monkeypatch):
    from drug_checker import import_greenbook

    db_path = tmp_path / "rejected.sqlite"
    conn = sqlite3.connect(db_path)
    assert create_all_tables(conn)
    conn.close()
    source = tmp_path / "invalid.json"
    source.write_text(json.dumps([
        {"productId": 12, "registrationNumber": "A4-0012", "productName": "Valid Fixture", "status": "Active"},
        {"productId": "bad", "registrationNumber": "A4-0013", "productName": "Invalid Fixture", "status": "Active"},
    ]), encoding="utf-8")
    monkeypatch.setattr(import_greenbook, "DB_PATH", db_path)
    monkeypatch.setattr(import_greenbook, "LOG_PATH", tmp_path / "rejected.log")

    assert import_greenbook.main([str(source)]) == 1
    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM drugs").fetchone()[0] == 0
    failed_run = conn.execute(
        "SELECT status, error_code, skipped_count, rejected_count "
        "FROM data_import_runs"
    ).fetchone()
    assert failed_run == ("error", "invalid_source_records", 1, 1)
    conn.close()


def test_import_history_adds_count_columns_without_rewriting_old_rows():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE data_import_runs (id INTEGER PRIMARY KEY, dataset TEXT NOT NULL, source_name TEXT NOT NULL, source_fetched_at TEXT, completed_at TEXT NOT NULL, status TEXT NOT NULL, row_count INTEGER, timestamp_anomaly INTEGER NOT NULL DEFAULT 0, anomaly_reason TEXT, error_code TEXT)")
    connection.execute("INSERT INTO data_import_runs(dataset, source_name, completed_at, status, row_count) VALUES ('registry', 'historic source', '2020-01-01T00:00:00+00:00', 'success', 20)")
    connection.commit()
    assert create_all_tables(connection)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(data_import_runs)")}
    assert {"imported_count", "updated_count", "skipped_count", "rejected_count", "duplicate_count"} <= columns
    historic = connection.execute("SELECT source_name, row_count FROM data_import_runs WHERE id=1").fetchone()
    assert tuple(historic) == ("historic source", 20)
    connection.close()


def test_dataset_status_exposes_recorded_import_counts(conn):
    now = datetime.now(timezone.utc)
    _record_success(conn, "registry", completed_at=now.isoformat(), fetched_at=(now - timedelta(days=1)).isoformat(), row_count=10)
    conn.execute("UPDATE data_import_runs SET imported_count=7, updated_count=2, skipped_count=1, rejected_count=0, duplicate_count=0 WHERE dataset='registry'")
    status = get_registry_data_status(conn, now=now)
    assert status["status"] == "loaded"
    assert status["imported_count"] == 7
    assert status["updated_count"] == 2
    assert status["skipped_count"] == 1
    assert status["rejected_count"] == 0
