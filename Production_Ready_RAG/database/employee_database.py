import sqlite3
from pathlib import Path


# ------------------------------------------------------------------
# IMPORTANT
# ------------------------------------------------------------------
# The path is resolved relative to THIS FILE, not to the current
# working directory. Otherwise "uvicorn api.main:socket_app" and
# "python database/read_all_data.py" can end up talking to two
# different SQLite files.
# ------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

DB_PATH = PROJECT_ROOT / "data" / "hr_employee.db"


class EmployeeDatabase:

    def __init__(self):

        DB_PATH.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self._create_tables()
        self._deduplicate()
        self._seed_data()

    # ====================================================
    # Connection
    # ====================================================

    def _get_connection(self):

        return sqlite3.connect(
            DB_PATH,
            check_same_thread=False
        )

    # ====================================================
    # Schema
    # ====================================================

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
                basic_salary REAL,
                email TEXT,
                phone TEXT,
                manager_name TEXT,
                location TEXT,
                employment_type TEXT,
                gender TEXT,
                date_of_birth TEXT
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

    # ====================================================
    # Remove duplicate rows created by earlier runs, then
    # add UNIQUE indexes so they can never come back.
    #
    # This is what caused "Annual/Casual/Sick/Personal" to
    # appear 4 times in the employee context.
    # ====================================================

    def _deduplicate(self):

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM leave_balances
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM leave_balances
                GROUP BY employee_id, leave_type
            )
        """)

        cursor.execute("""
            DELETE FROM leave_transactions
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM leave_transactions
                GROUP BY employee_id, leave_type,
                         leave_date, days
            )
        """)

        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_leave_balances_unique
            ON leave_balances (employee_id, leave_type)
        """)

        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS
                idx_leave_transactions_unique
            ON leave_transactions (
                employee_id, leave_type, leave_date, days
            )
        """)

        conn.commit()
        conn.close()

    # ====================================================
    # Seed demo data (idempotent)
    # ====================================================

    def _seed_data(self):

        conn = self._get_connection()
        cursor = conn.cursor()

        employees = [
            (
                "employee-001",
                "Arun Kumar",
                "Software Engineer",
                "Engineering",
                "2024-01-10",
                "Active",
                65000,
                "arun.kumar@company.com",
                "+91-98765-43210",
                "Priya Raghunathan",
                "Coimbatore, IN",
                "Full-Time",
                "Male",
                "1996-03-22",
            ),
            (
                "employee-002",
                "Sneha Reddy",
                "Product Analyst",
                "Product",
                "2023-06-19",
                "Active",
                72000,
                "sneha.reddy@company.com",
                "+91-91234-56789",
                "Vikram Nair",
                "Bengaluru, IN",
                "Full-Time",
                "Female",
                "1994-11-08",
            ),
        ]

        cursor.executemany("""
            INSERT OR IGNORE INTO employees (
                employee_id,
                name,
                designation,
                department,
                join_date,
                status,
                basic_salary,
                email,
                phone,
                manager_name,
                location,
                employment_type,
                gender,
                date_of_birth
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, employees)

        leave_balances = [
            # employee-001
            ("employee-001", "Annual", 18, 15, 3),
            ("employee-001", "Casual", 12, 4, 8),
            ("employee-001", "Sick", 12, 2, 10),
            ("employee-001", "Personal", 5, 2, 3),

            # employee-002
            ("employee-002", "Annual", 20, 9, 11),
            ("employee-002", "Casual", 12, 5, 7),
            ("employee-002", "Sick", 10, 3, 7),
            ("employee-002", "Personal", 5, 1, 4),
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

        transactions = [
            # ---------------- employee-001 ----------------
            ("employee-001", "Annual", "2026-01-15", 1, "Family function", "Approved"),
            ("employee-001", "Annual", "2026-02-09", 1, "Wedding anniversary", "Approved"),
            ("employee-001", "Annual", "2026-03-20", 2, "Travel to hometown", "Approved"),
            ("employee-001", "Annual", "2026-04-14", 1, "Festival", "Approved"),
            ("employee-001", "Annual", "2026-05-02", 3, "Vacation trip", "Approved"),
            ("employee-001", "Annual", "2026-06-18", 2, "Family event", "Approved"),
            ("employee-001", "Annual", "2026-07-10", 2, "Personal travel", "Approved"),
            ("employee-001", "Annual", "2026-07-11", 1, "Personal travel", "Approved"),
            ("employee-001", "Annual", "2026-07-27", 2, "Vacation", "Approved"),

            ("employee-001", "Sick", "2026-02-27", 1, "Fever", "Approved"),
            ("employee-001", "Sick", "2026-05-19", 1, "Viral infection", "Approved"),

            ("employee-001", "Casual", "2026-01-06", 1, "Personal errand", "Approved"),
            ("employee-001", "Casual", "2026-03-03", 1, "House shifting", "Approved"),
            ("employee-001", "Casual", "2026-04-24", 1, "Bank work", "Approved"),
            ("employee-001", "Casual", "2026-08-12", 1, "Family commitment", "Approved"),

            ("employee-001", "Personal", "2026-08-05", 1, "Personal work", "Approved"),
            ("employee-001", "Personal", "2026-08-06", 1, "Personal work", "Approved"),

            ("employee-001", "Annual", "2026-08-24", 1, "Long weekend trip", "Pending"),

            # ---------------- employee-002 ----------------
            ("employee-002", "Annual", "2026-01-22", 2, "Trip to Goa", "Approved"),
            ("employee-002", "Annual", "2026-02-14", 1, "Personal celebration", "Approved"),
            ("employee-002", "Annual", "2026-03-30", 2, "Sister's wedding", "Approved"),
            ("employee-002", "Annual", "2026-05-08", 3, "Family vacation", "Approved"),
            ("employee-002", "Annual", "2026-06-25", 1, "Festival", "Approved"),

            ("employee-002", "Sick", "2026-02-04", 1, "Cold and cough", "Approved"),
            ("employee-002", "Sick", "2026-04-11", 2, "Migraine", "Approved"),

            ("employee-002", "Casual", "2026-01-09", 1, "Personal errand", "Approved"),
            ("employee-002", "Casual", "2026-03-16", 1, "Vehicle service", "Approved"),
            ("employee-002", "Casual", "2026-06-02", 1, "Doctor visit", "Approved"),
            ("employee-002", "Casual", "2026-08-14", 2, "Home renovation work", "Approved"),

            ("employee-002", "Personal", "2026-07-21", 1, "Personal work", "Approved"),

            ("employee-002", "Annual", "2026-08-28", 2, "Short getaway", "Pending"),
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

        if not employee_id:
            return None

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
                basic_salary,
                email,
                phone,
                manager_name,
                location,
                employment_type,
                gender,
                date_of_birth
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
            "email": row[7],
            "phone": row[8],
            "manager_name": row[9],
            "location": row[10],
            "employment_type": row[11],
            "gender": row[12],
            "date_of_birth": row[13],
        }

    # ====================================================
    # Leave balance
    # ====================================================

    def get_leave_balances(self, employee_id):

        if not employee_id:
            return []

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
            ORDER BY leave_type
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

        if not employee_id:
            return []

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

        return self._map_transactions(rows)

    # ====================================================
    # Leaves in an arbitrary date range
    # ====================================================

    def get_leaves_between(
        self,
        employee_id,
        start_date,
        end_date,
        statuses=("Approved",)
    ):

        if not employee_id:
            return []

        if not statuses:
            statuses = ("Approved",)

        placeholders = ", ".join("?" for _ in statuses)

        query = f"""
            SELECT
                leave_type,
                leave_date,
                days,
                reason,
                status
            FROM leave_transactions
            WHERE employee_id = ?
              AND leave_date BETWEEN ? AND ?
              AND status IN ({placeholders})
            ORDER BY leave_date
        """

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            query,
            (
                employee_id,
                start_date,
                end_date,
                *statuses
            )
        )

        rows = cursor.fetchall()

        conn.close()

        return self._map_transactions(rows)

    # ====================================================
    # Full leave history
    # ====================================================

    def get_all_leave_transactions(
        self,
        employee_id,
        limit=100
    ):

        if not employee_id:
            return []

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
            ORDER BY leave_date DESC
            LIMIT ?
        """, (employee_id, limit))

        rows = cursor.fetchall()

        conn.close()

        return self._map_transactions(rows)

    # ====================================================
    # Salary
    # ====================================================

    def get_salary(self, employee_id):

        if not employee_id:
            return None

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

    # ====================================================
    # Helpers
    # ====================================================

    @staticmethod
    def _map_transactions(rows):

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
