from employee.employee_data_service import EmployeeDataService


class EmployeeContextBuilder:

    def __init__(self):

        self.employee_service = (
            EmployeeDataService()
        )

    def build(
        self,
        employee_id,
        query_type
    ):

        if query_type == "profile":

            employee = (
                self.employee_service
                .get_profile(employee_id)
            )

            return {
                "type": "employee_profile",
                "data": employee
            }

        if query_type == "leave_balance":

            balances = (
                self.employee_service
                .get_leave_balance(employee_id)
            )

            return {
                "type": "leave_balance",
                "data": balances
            }

        if query_type == "leave_history":

            leaves = (
                self.employee_service
                .get_current_month_leave(
                    employee_id
                )
            )

            return {
                "type": "current_month_leave",
                "data": leaves
            }

        if query_type == "salary":

            salary = (
                self.employee_service
                .get_salary(employee_id)
            )

            return {
                "type": "salary",
                "data": {
                    "basic_salary": salary
                }
            }

        return None