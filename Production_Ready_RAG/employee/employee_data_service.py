from datetime import datetime, timedelta

from database.employee_database import EmployeeDatabase


class EmployeeDataService:
    """
    Thin, read-only service layer over the employee database.

    Every method takes the employee_id that the backend derived
    from the authenticated session. It is NEVER taken from the
    user's message.
    """

    def __init__(self):

        self.db = EmployeeDatabase()

    # ------------------------------------------------
    # Employee profile
    # ------------------------------------------------

    def get_profile(self, employee_id):

        return self.db.get_employee(employee_id)

    # ------------------------------------------------
    # Leave balances
    # ------------------------------------------------

    def get_leave_balance(self, employee_id):

        return self.db.get_leave_balances(employee_id)

    # ------------------------------------------------
    # Current month leave (kept for compatibility)
    # ------------------------------------------------

    def get_current_month_leave(self, employee_id):

        now = datetime.now()

        return self.db.get_current_month_leaves(
            employee_id,
            now.year,
            now.month
        )

    # ------------------------------------------------
    # Rich leave history: week + month + upcoming + YTD
    # ------------------------------------------------

    def get_leave_history(self, employee_id):

        now = datetime.now()

        # Monday of the current week
        week_start = now - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=6)

        week_start_str = week_start.strftime("%Y-%m-%d")
        week_end_str = week_end.strftime("%Y-%m-%d")

        this_week = self.db.get_leaves_between(
            employee_id=employee_id,
            start_date=week_start_str,
            end_date=week_end_str,
            statuses=("Approved",)
        )

        this_month = self.db.get_current_month_leaves(
            employee_id,
            now.year,
            now.month
        )

        upcoming = self.db.get_leaves_between(
            employee_id=employee_id,
            start_date=now.strftime("%Y-%m-%d"),
            end_date=f"{now.year}-12-31",
            statuses=("Approved", "Pending")
        )

        year_rows = self.db.get_leaves_between(
            employee_id=employee_id,
            start_date=f"{now.year}-01-01",
            end_date=f"{now.year}-12-31",
            statuses=("Approved",)
        )

        year_total = sum(
            (row.get("days") or 0)
            for row in year_rows
        )

        return {
            "week_start": week_start_str,
            "week_end": week_end_str,
            "month_label": now.strftime("%B %Y"),
            "this_week": this_week,
            "this_month": this_month,
            "upcoming": upcoming,
            "year_total_days": year_total
        }

    # ------------------------------------------------
    # Salary
    # ------------------------------------------------

    def get_salary(self, employee_id):

        return self.db.get_salary(employee_id)
