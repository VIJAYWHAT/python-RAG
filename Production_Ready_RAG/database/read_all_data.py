import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DB_PATH = PROJECT_ROOT / "database" / "hr_queries.db"


def print_table(cursor, table_name):

    print(f"\n===== {table_name.upper()} =====")

    cursor.execute(f"SELECT * FROM {table_name}")
    rows = cursor.fetchall()

    column_names = [
        description[0]
        for description in cursor.description
    ]

    print(" | ".join(column_names))

    if not rows:
        print("(no rows)")
        return

    for row in rows:
        print(" | ".join(str(value) for value in row))

    print(f"({len(rows)} row(s))")


if __name__ == "__main__":

    print(f"Database file: {DB_PATH}")
    print(f"Exists       : {DB_PATH.exists()}")

    if not DB_PATH.exists():
        print(
            "\nThe database file does not exist yet.\n"
            "Run:  python database/init_database.py"
        )
        raise SystemExit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print_table(cursor, "hr_queries")
    # print_table(cursor, "leave_balances")
    # print_table(cursor, "leave_transactions")

    conn.close()
