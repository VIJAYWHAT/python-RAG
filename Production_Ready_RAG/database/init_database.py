import sys
from pathlib import Path

# Allow running this file directly:
#   python database/init_database.py
# as well as from the project root:
#   python -m database.init_database

PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.employee_database import EmployeeDatabase, DB_PATH


if __name__ == "__main__":

    print("Initializing employee database...")
    print(f"Database file: {DB_PATH}")

    EmployeeDatabase()

    print("Employee database initialized successfully.")
