"""
Verifies the employee-data chain WITHOUT calling the LLM.

Run from the project root:

    python verify_employee_flow.py

It checks, layer by layer:

    1. Database file location + connection
    2. employees / leave_balances / leave_transactions rows
    3. Duplicate detection
    4. Intent routing (which questions go to the DB vs RAG)
    5. The exact employee context block that is injected
       into the LLM prompt
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database.employee_database import EmployeeDatabase, DB_PATH
from employee.employee_query_detector import EmployeeQueryDetector
from employee.employee_context_builder import EmployeeContextBuilder


EMPLOYEE_ID = "employee-001"


def banner(title):
    print("\n" + "=" * 62)
    print(title)
    print("=" * 62)


# ==================================================================
# 1. Database
# ==================================================================

def check_database():

    banner("STEP 1 - DATABASE CONNECTION")

    print(f"Database file : {DB_PATH}")
    print(f"Exists        : {DB_PATH.exists()}")

    db = EmployeeDatabase()

    conn = db._get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' ORDER BY name"
    )

    tables = [row[0] for row in cursor.fetchall()]

    print(f"Tables        : {tables}")

    for table in ("employees", "leave_balances", "leave_transactions"):

        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        print(f"  {table:<20} {cursor.fetchone()[0]} row(s)")

    # duplicate check
    cursor.execute("""
        SELECT employee_id, leave_type, COUNT(*)
        FROM leave_balances
        GROUP BY employee_id, leave_type
        HAVING COUNT(*) > 1
    """)

    duplicates = cursor.fetchall()

    if duplicates:
        print("\n  !! DUPLICATE leave_balances rows found:")
        for row in duplicates:
            print(f"     {row}")
    else:
        print("\n  No duplicate leave_balances rows. OK")

    conn.close()

    return db


# ==================================================================
# 2. Employee record
# ==================================================================

def check_employee(db):

    banner(f"STEP 2 - EMPLOYEE RECORD ({EMPLOYEE_ID})")

    profile = db.get_employee(EMPLOYEE_ID)

    if not profile:
        print("!! NO RECORD FOUND. The chatbot cannot answer "
              "personal questions for this user.")
        return False

    for key, value in profile.items():
        print(f"  {key:<18}: {value}")

    print("\n  Leave balances:")

    for row in db.get_leave_balances(EMPLOYEE_ID):
        print(
            f"    {row['leave_type']:<10} "
            f"total={row['total_days']:<3} "
            f"used={row['used_days']:<3} "
            f"remaining={row['remaining_days']}"
        )

    return True


# ==================================================================
# 3. Intent routing
# ==================================================================

PERSONAL_QUESTIONS = [
    "tell my name",
    "what is my name",
    "who am i",
    "what is my employee id",
    "what is my department",
    "what is my designation",
    "who is my manager",
    "when did i join",
    "what is my joining date",
    "what is my work location",
    "what is my official email",
    "what is my salary",
    "how much do i get paid",
    "how many leaves remaining for me to this week",
    "what is my leave balance",
    "how many casual leaves do i have left",
    "how many leaves have i taken this month",
    "how many sick leaves have i used",
    "show my profile",
    "how long have i been working here",
]

POLICY_QUESTIONS = [
    "tell me about casual leave",
    "tell me about all the leaves",
    "tell me about your company",
    "what is the annual leave policy",
    "how many days of sick leave do employees get",
    "what is the resignation notice period",
    "what are the working hours",
    "show me the maternity leave policy",
    "give me the code of conduct",
    "hi",
]


def check_routing():

    banner("STEP 3 - INTENT ROUTING")

    failures = 0

    print("\nExpected route: EMPLOYEE DATABASE\n")

    for question in PERSONAL_QUESTIONS:

        result = EmployeeQueryDetector.classify(question)

        ok = result["is_employee_query"]

        if not ok:
            failures += 1

        print(
            f"  [{'OK  ' if ok else 'FAIL'}] "
            f"{question:<52} -> "
            f"{result['query_types']}"
        )

    print("\nExpected route: HR KNOWLEDGE BASE (RAG)\n")

    for question in POLICY_QUESTIONS:

        result = EmployeeQueryDetector.classify(question)

        ok = not result["is_employee_query"]

        if not ok:
            failures += 1

        print(
            f"  [{'OK  ' if ok else 'FAIL'}] "
            f"{question:<52} -> "
            f"{'DB' if result['is_employee_query'] else 'RAG'}"
        )

    total = len(PERSONAL_QUESTIONS) + len(POLICY_QUESTIONS)

    print(f"\n  Routing: {total - failures}/{total} correct")

    return failures == 0


# ==================================================================
# 4. Context that reaches the LLM
# ==================================================================

def check_context():

    banner("STEP 4 - CONTEXT INJECTED INTO THE LLM PROMPT")

    builder = EmployeeContextBuilder()

    samples = [
        "tell my name",
        "what is my salary",
        "how many leaves remaining for me to this week",
        "how many leaves have i taken this month",
    ]

    for question in samples:

        classification = EmployeeQueryDetector.classify(question)

        context = builder.build(
            employee_id=EMPLOYEE_ID,
            query_types=classification["query_types"]
        )

        print("\n" + "-" * 62)
        print(f"QUESTION    : {question}")
        print(f"QUERY TYPES : {classification['query_types']}")
        print(f"FOUND       : {context['found']}")
        print("-" * 62)
        print(context["text"])


# ==================================================================

if __name__ == "__main__":

    db = check_database()

    has_employee = check_employee(db)

    routing_ok = check_routing()

    if has_employee:
        check_context()

    banner("SUMMARY")

    print(f"  Database reachable      : yes")
    print(f"  Employee record present : {'yes' if has_employee else 'NO'}")
    print(f"  Routing correct         : {'yes' if routing_ok else 'NO'}")

    if has_employee and routing_ok:
        print(
            "\n  The employee-data chain is healthy. "
            "Restart the API and retry from Flutter."
        )
    else:
        print(
            "\n  Fix the failing layer above before testing "
            "through the chatbot."
        )
