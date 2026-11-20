import sqlite3

import pytest

from drug_checker import seed_demo_alerts
from drug_checker.db_ops import get_alert_data_status
from drug_checker.db_setup import create_all_tables
from drug_checker.engine import check_reg_number
from drug_checker.sms_replies import build_sms


@pytest.fixture
def demo_db(tmp_path, monkeypatch):
    path = tmp_path / "demo-alerts.sqlite3"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    assert create_all_tables(conn)
    conn.close()
    monkeypatch.setattr(seed_demo_alerts, "DB_PATH", path)
    return path


def test_demo_alert_seed_is_explicit_synthetic_and_idempotent(demo_db, capsys):
    assert seed_demo_alerts.main() == 0
    first_output = capsys.readouterr().out
    assert "SYNTHETIC" in first_output
    assert "not a real NAFDAC notice" in first_output
    assert seed_demo_alerts.main() == 0
    assert "already exists" in capsys.readouterr().out

    conn = sqlite3.connect(demo_db)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM alerts").fetchall()
    assert len(rows) == 1
    assert rows[0]["source_kind"] == "synthetic"
    assert "SYNTHETIC — DEMONSTRATION ONLY" in rows[0]["reason"]
    assert conn.execute("SELECT COUNT(*) FROM data_import_runs WHERE dataset='alerts'").fetchone()[0] == 0
    assert get_alert_data_status(conn)["status"] == "unknown"
    conn.close()


def test_synthetic_alert_is_labelled_in_backend_and_sms(demo_db):
    assert seed_demo_alerts.main() == 0
    conn = sqlite3.connect(demo_db)
    conn.row_factory = sqlite3.Row
    findings = check_reg_number(conn, "ZZ-0001")
    conn.close()
    assert findings["status"] == "not_found"
    assert findings["alerts"][0]["source_kind"] == "synthetic"
    assert findings["alerts"][0]["demo_label"] == "SYNTHETIC — DEMONSTRATION ONLY"
    assert findings["alert_data_status"]["status"] == "unknown"
    reply = build_sms(findings)
    assert "synthetic" in reply.casefold()
    assert "not a real nafdac notice" in reply.casefold()


def test_invalid_source_kind_is_rejected(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    assert create_all_tables(conn)
    from drug_checker.db_ops import add_alert
    with pytest.raises(ValueError, match="source_kind"):
        add_alert(conn, {
            "product_name": "Synthetic Fixture",
            "alert_type": "warning",
            "alert_date": "2026-01-01",
            "source_link": "https://example.invalid/fixture",
            "source_kind": "real-ish",
        })
