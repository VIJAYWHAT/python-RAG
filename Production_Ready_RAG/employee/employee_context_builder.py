from datetime import datetime, timedelta

from employee.employee_data_service import EmployeeDataService


class EmployeeContextBuilder:
    """
    Turns the authenticated employee's database record into a
    readable text block that is injected into the LLM prompt.

    IMPORTANT:
    - employee_id ALWAYS comes from the authenticated session,
      never from the user's message.
    - Sensitive fields (salary) are only included when the
      question actually asks for them.
    """

    MONEY_FIELDS = {"basic_salary"}

    def __init__(self):

        self.employee_service = EmployeeDataService()

    # ================================================================
    # Public API
    # ================================================================

    def build(self, employee_id, query_types=None):
        """
        Returns:
            {
                "employee_id": "...",
                "found": True/False,
                "query_types": [...],
                "text": "<formatted block for the prompt>",
                "data": {...}   # raw data, for logging/debug
            }
        """

        if not query_types:
            query_types = ["profile"]

        if isinstance(query_types, str):
            query_types = [query_types]

        profile = self.employee_service.get_profile(employee_id)

        if not profile:

            return {
                "employee_id": employee_id,
                "found": False,
                "query_types": query_types,
                "text": "",
                "data": {}
            }

        sections = []
        data = {}

        # ------------------------------------------------------------
        # Identity block - always included so the assistant knows
        # who it is talking to.
        # ------------------------------------------------------------

        include_salary = "salary" in query_types

        sections.append(
            self._format_profile(
                profile,
                include_salary=include_salary
            )
        )

        data["profile"] = {
            key: value
            for key, value in profile.items()
            if include_salary or key not in self.MONEY_FIELDS
        }

        # ------------------------------------------------------------
        # Leave balance
        # ------------------------------------------------------------

        if (
            "leave_balance" in query_types
            or "leave_history" in query_types
        ):

            balances = self.employee_service.get_leave_balance(
                employee_id
            )

            data["leave_balances"] = balances

            sections.append(
                self._format_leave_balances(balances)
            )

        # ------------------------------------------------------------
        # Leave history (current month + current week + upcoming)
        # ------------------------------------------------------------

        if "leave_history" in query_types:

            history = self.employee_service.get_leave_history(
                employee_id
            )

            data["leave_history"] = history

            sections.append(
                self._format_leave_history(history)
            )

        # ------------------------------------------------------------

        text = "\n\n".join(
            section
            for section in sections
            if section
        )

        return {
            "employee_id": employee_id,
            "found": True,
            "query_types": query_types,
            "text": text,
            "data": data
        }

    # ================================================================
    # Formatting helpers
    # ================================================================

    def _format_profile(self, profile, include_salary=False):

        lines = [
            "EMPLOYEE RECORD (the authenticated user who is asking):",
            f"- Employee ID    : {self._value(profile.get('employee_id'))}",
            f"- Full Name      : {self._value(profile.get('name'))}",
            f"- Designation    : {self._value(profile.get('designation'))}",
            f"- Department     : {self._value(profile.get('department'))}",
            f"- Reporting Manager : {self._value(profile.get('manager_name'))}",
            f"- Date of Joining: {self._value(profile.get('join_date'))}",
            f"- Employment Type: {self._value(profile.get('employment_type'))}",
            f"- Work Location  : {self._value(profile.get('location'))}",
            f"- Employment Status : {self._value(profile.get('status'))}",
            f"- Official Email : {self._value(profile.get('email'))}",
            f"- Contact Number : {self._value(profile.get('phone'))}",
            f"- Date of Birth  : {self._value(profile.get('date_of_birth'))}",
            f"- Gender         : {self._value(profile.get('gender'))}",
        ]

        join_date = profile.get("join_date")

        tenure = self._tenure_text(join_date)

        if tenure:
            lines.append(f"- Tenure         : {tenure}")

        if include_salary:

            salary = profile.get("basic_salary")

            lines.append(
                f"- Basic Salary   : "
                f"{self._money(salary)} per month"
            )

        return "\n".join(lines)

    def _format_leave_balances(self, balances):

        if not balances:

            return (
                "LEAVE BALANCE:\n"
                "No leave balance records found for this employee."
            )

        lines = [
            f"LEAVE BALANCE (as on {self._today_text()}):",
            "Leave Type | Total Days | Used Days | Remaining Days",
            "-----------|------------|-----------|---------------"
        ]

        total_all = 0
        used_all = 0
        remaining_all = 0

        for row in balances:

            lines.append(
                f"{row.get('leave_type')} | "
                f"{row.get('total_days')} | "
                f"{row.get('used_days')} | "
                f"{row.get('remaining_days')}"
            )

            total_all += row.get("total_days") or 0
            used_all += row.get("used_days") or 0
            remaining_all += row.get("remaining_days") or 0

        lines.append("")

        lines.append(
            f"Overall totals -> Total entitlement: {total_all} days | "
            f"Used: {used_all} days | "
            f"Remaining: {remaining_all} days"
        )

        return "\n".join(lines)

    def _format_leave_history(self, history):

        if not history:
            return ""

        blocks = []

        this_week = history.get("this_week") or []
        this_month = history.get("this_month") or []
        upcoming = history.get("upcoming") or []
        year_total = history.get("year_total_days")

        blocks.append(
            self._format_transactions(
                f"LEAVE TAKEN THIS WEEK "
                f"({history.get('week_start')} to "
                f"{history.get('week_end')})",
                this_week,
                empty_text="No leave taken this week."
            )
        )

        blocks.append(
            self._format_transactions(
                f"LEAVE TAKEN THIS MONTH "
                f"({history.get('month_label')})",
                this_month,
                empty_text="No leave taken this month."
            )
        )

        if upcoming:

            blocks.append(
                self._format_transactions(
                    "UPCOMING / PENDING LEAVE REQUESTS",
                    upcoming,
                    empty_text="No upcoming leave requests."
                )
            )

        if year_total is not None:

            blocks.append(
                f"TOTAL APPROVED LEAVE DAYS TAKEN IN "
                f"{datetime.now().year}: {year_total} days"
            )

        return "\n\n".join(
            block
            for block in blocks
            if block
        )

    def _format_transactions(self, title, rows, empty_text):

        if not rows:
            return f"{title}:\n{empty_text}"

        lines = [f"{title}:"]

        for row in rows:

            lines.append(
                f"- {row.get('leave_date')} | "
                f"{row.get('leave_type')} Leave | "
                f"{row.get('days')} day(s) | "
                f"Reason: {row.get('reason') or 'N/A'} | "
                f"Status: {row.get('status')}"
            )

        return "\n".join(lines)

    # ================================================================
    # Small utilities
    # ================================================================

    @staticmethod
    def _value(value):

        if value is None or value == "":
            return "Not available"

        return value

    @staticmethod
    def _money(value):

        if value is None:
            return "Not available"

        try:
            return f"INR {float(value):,.2f}"

        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _today_text():

        return datetime.now().strftime("%d %B %Y")

    @staticmethod
    def _tenure_text(join_date):

        if not join_date:
            return None

        try:
            joined = datetime.strptime(
                str(join_date)[:10],
                "%Y-%m-%d"
            )

        except ValueError:
            return None

        days = (datetime.now() - joined).days

        if days < 0:
            return None

        years = days // 365
        months = (days % 365) // 30

        if years and months:
            return f"{years} year(s) {months} month(s)"

        if years:
            return f"{years} year(s)"

        return f"{months} month(s)"
