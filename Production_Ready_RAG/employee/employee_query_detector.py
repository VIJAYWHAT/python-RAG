import re


class EmployeeQueryDetector:

    PERSONAL_PATTERNS = [

        # Leave balance
        r"\bmy leave\b",
        r"\bhow many leaves do i have\b",
        r"\bhow much leave do i have\b",
        r"\bleave balance\b",
        r"\bremaining leaves\b",
        r"\bleaves remaining\b",

        # Leave history
        r"\bleave.*taken\b",
        r"\bleaves.*taken\b",
        r"\bhow many leaves.*taken\b",
        r"\bhow much leave.*taken\b",
        r"\bmy leave history\b",

        # Salary
        r"\bmy salary\b",
        r"\bwhat is my salary\b",
        r"\bhow much.*salary.*i\b",
        r"\bmy pay\b",

        # Employee profile
        r"\bmy profile\b",
        r"\bmy department\b",
        r"\bmy designation\b",
        r"\bmy joining date\b",
        r"\bwhen did i join\b",
    ]

    @classmethod
    def is_employee_query(cls, question):

        question = question.lower().strip()

        for pattern in cls.PERSONAL_PATTERNS:

            if re.search(
                pattern,
                question
            ):
                return True

        return False

    @classmethod
    def get_query_type(cls, question):

        question = question.lower()

        if (
            "salary" in question
            or "pay" in question
        ):
            return "salary"

        if (
            "taken" in question
            or "history" in question
        ):
            return "leave_history"

        if (
            "leave" in question
            or "leaves" in question
        ):
            return "leave_balance"

        if (
            "profile" in question
            or "department" in question
            or "designation" in question
            or "joining" in question
            or "join" in question
        ):
            return "profile"

        return None