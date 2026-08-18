import sqlite3
from pathlib import Path


DB_PATH = Path("data/hr_employee.db")


class EmployeeDatabase:

    def __init__(self):
        DB_PATH.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self._create_tables()
        self._seed_data()

    def _get_connection(self):
        return sqlite3.connect(
            DB_PATH,
            check_same_thread=False
        )

    def _create_tables(self):

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                employee_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                designation TEXT,
                department TEXT,
                join_date TEXT,
                status TEXT,
                basic_salary REAL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leave_balances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                leave_type TEXT NOT NULL,
                total_days INTEGER NOT NULL,
                used_days INTEGER NOT NULL,
                remaining_days INTEGER NOT NULL,
                FOREIGN KEY(employee_id)
                    REFERENCES employees(employee_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS leave_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT NOT NULL,
                leave_type TEXT NOT NULL,
                leave_date TEXT NOT NULL,
                days INTEGER NOT NULL,
                reason TEXT,
                status TEXT DEFAULT 'Approved',
                FOREIGN KEY(employee_id)
                    REFERENCES employees(employee_id)
            )
        """)

        conn.commit()
        conn.close()

    def _seed_data(self):

        conn = self._get_connection()
        cursor = conn.cursor()

        # ------------------------------------------------
        # Employee
        # ------------------------------------------------

        cursor.execute("""
            INSERT OR IGNORE INTO employees (
                employee_id,
                name,
                designation,
                department,
                join_date,
                status,
                basic_salary
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "employee-001",
            "Arun Kumar",
            "Software Engineer",
            "Engineering",
            "2024-01-10",
            "Active",
            65000
        ))

        # ------------------------------------------------
        # Leave balances
        # ------------------------------------------------

        leave_balances = [
            (
                "employee-001",
                "Annual",
                18,
                15,
                3
            ),
            (
                "employee-001",
                "Casual",
                12,
                1,
                11
            ),
            (
                "employee-001",
                "Sick",
                12,
                0,
                12
            ),
            (
                "employee-001",
                "Personal",
                5,
                2,
                3
            ),
        ]

        cursor.executemany("""
            INSERT OR IGNORE INTO leave_balances (
                employee_id,
                leave_type,
                total_days,
                used_days,
                remaining_days
            )
            VALUES (?, ?, ?, ?, ?)
        """, leave_balances)

        # ------------------------------------------------
        # Leave transactions
        # ------------------------------------------------

        transactions = [
            (
                "employee-001",
                "Personal",
                "2026-08-05",
                1,
                "Personal work",
                "Approved"
            ),
            (
                "employee-001",
                "Personal",
                "2026-08-06",
                1,
                "Personal work",
                "Approved"
            ),
            (
                "employee-001",
                "Casual",
                "2026-08-12",
                1,
                "Family commitment",
                "Approved"
            ),
        ]

        cursor.executemany("""
            INSERT OR IGNORE INTO leave_transactions (
                employee_id,
                leave_type,
                leave_date,
                days,
                reason,
                status
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, transactions)

        conn.commit()
        conn.close()

    # ====================================================
    # Employee profile
    # ====================================================

    def get_employee(self, employee_id):

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                employee_id,
                name,
                designation,
                department,
                join_date,
                status,
                basic_salary
            FROM employees
            WHERE employee_id = ?
        """, (employee_id,))

        row = cursor.fetchone()

        conn.close()

        if not row:
            return None

        return {
            "employee_id": row[0],
            "name": row[1],
            "designation": row[2],
            "department": row[3],
            "join_date": row[4],
            "status": row[5],
            "basic_salary": row[6],
        }

    # ====================================================
    # Leave balance
    # ====================================================

    def get_leave_balances(self, employee_id):

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                leave_type,
                total_days,
                used_days,
                remaining_days
            FROM leave_balances
            WHERE employee_id = ?
        """, (employee_id,))

        rows = cursor.fetchall()

        conn.close()

        return [
            {
                "leave_type": row[0],
                "total_days": row[1],
                "used_days": row[2],
                "remaining_days": row[3],
            }
            for row in rows
        ]

    # ====================================================
    # This month's leaves
    # ====================================================

    def get_current_month_leaves(
        self,
        employee_id,
        year,
        month
    ):

        month_prefix = f"{year:04d}-{month:02d}"

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                leave_type,
                leave_date,
                days,
                reason,
                status
            FROM leave_transactions
            WHERE employee_id = ?
              AND leave_date LIKE ?
              AND status = 'Approved'
            ORDER BY leave_date
        """, (
            employee_id,
            f"{month_prefix}%"
        ))

        rows = cursor.fetchall()

        conn.close()

        return [
            {
                "leave_type": row[0],
                "leave_date": row[1],
                "days": row[2],
                "reason": row[3],
                "status": row[4],
            }
            for row in rows
        ]

    # ====================================================
    # Salary
    # ====================================================

    def get_salary(self, employee_id):

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT basic_salary
            FROM employees
            WHERE employee_id = ?
        """, (employee_id,))

        row = cursor.fetchone()

        conn.close()

        if not row:
            return None

        return row[0]