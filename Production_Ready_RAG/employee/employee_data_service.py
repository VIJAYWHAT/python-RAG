from datetime import datetime

from database.employee_database import EmployeeDatabase


class EmployeeDataService:

    def __init__(self):

        self.db = EmployeeDatabase()

    # ------------------------------------------------
    # Employee profile
    # ------------------------------------------------

    def get_profile(self, employee_id):

        return self.db.get_employee(
            employee_id
        )

    # ------------------------------------------------
    # Leave balances
    # ------------------------------------------------

    def get_leave_balance(self, employee_id):

        return self.db.get_leave_balances(
            employee_id
        )

    # ------------------------------------------------
    # Current month leave
    # ------------------------------------------------

    def get_current_month_leave(
        self,
        employee_id
    ):

        now = datetime.now()

        return self.db.get_current_month_leaves(
            employee_id,
            now.year,
            now.month
        )

    # ------------------------------------------------
    # Salary
    # ------------------------------------------------

    def get_salary(self, employee_id):

        return self.db.get_salary(
            employee_id
        )