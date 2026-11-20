"""Try the database from the terminal.

Put this file in the PROJECT ROOT (next to the drug_checker folder), then:

    python try_search.py ventolin
    python try_search.py loperamide
    python try_search.py A4-102611        (anything with a digit is also tried as a reg number)

CHANGE the word below if your package folder has a different name.
"""
import sys

from drug_checker.config import DB_PATH          # <- your package name here
from drug_checker.database import create_connection
from drug_checker.db_ops import (
    count_drugs, find_alerts, find_by_name, find_by_reg_number,
)

RANK_MEANING = {
    0: "exact name",
    1: "name starts with it",
    2: "a word in the name",
    3: "active ingredient only",
}


def show(row, how):
    print(f"  - {row['brand_name']}  [{row['reg_number']}]  ({how})")
    print(f"      ingredients: {row['generic_name']}")
    print(f"      maker: {row['manufacturer']}  |  strength: {row['strength']}"
          f"  |  form: {row['dosage_form']}")
    print(f"      registry status: {row['registry_status']}"
          f"  |  source: {row['source']}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python try_search.py <drug name or reg number>")
        return 1

    text = " ".join(sys.argv[1:])

    conn = create_connection(DB_PATH)
    if conn is None:
        print("Could not open the database. Did you run init_db?")
        return 1

    try:
        print(f"Database holds {count_drugs(conn)} products.\n")

        print(f"Search by NAME for {text!r}:")
        rows = find_by_name(conn, text)
        for row in rows:
            show(row, RANK_MEANING[row["match_rank"]])
        if not rows:
            print("  (nothing found)")

        if any(ch.isdigit() for ch in text):
            print(f"\nSearch by REG NUMBER for {text!r}:")
            rows = find_by_reg_number(conn, text)
            for row in rows:
                show(row, "reg number match")
            if not rows:
                print("  (nothing found)")

        alerts = find_alerts(conn, reg_number=text if any(c.isdigit() for c in text) else None,
                             name=text)
        print(f"\nAlerts on record: {len(alerts)}")
        for alert in alerts:
            print(f"  - {alert['alert_type']} on {alert['alert_date']}: "
                  f"{alert['product_name']} ({alert['source_link']})")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
