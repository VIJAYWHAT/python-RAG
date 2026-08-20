"""
Ejadah API route names.

These mirror `class ApiRoute` in the Flutter app's
lib/src/config/ejadhaconfig.dart. Only the read-only routes the
chatbot needs are listed - the assistant answers questions, it
never submits requests on the employee's behalf.

If a route is added here, it must be read-only. Anything that
mutates HR data (applyLeaveRequest, changePassword, ...) stays out
on purpose: a prompt-injected model must not be able to reach it.
"""


class EjadahRoute:

    # --------------------------------------------------------------
    # Identity / profile
    # --------------------------------------------------------------

    # Body: {"EmployeeNumber": "<id>"}
    # Response.EmployeeList -> [ { EMPLOYEENUMBER, EMPLOYEENAME, ... } ]
    GET_EMPLOYEE_INFO = "getEmployeeInfo"

    # --------------------------------------------------------------
    # Leave
    # --------------------------------------------------------------

    # Body: {"EmployeeId": "<id>", "LeaveType": null}
    # Response.LeaveBalance -> number
    GET_LEAVE_BALANCE = "getLeaveBalance"

    # Body: {"EmployeeNumber": "<id>"}
    # Response.LeaveHistoryRecord -> [ { ABSENCE_TYPE, START_DATE, ... } ]
    GET_LEAVE_HISTORY = "getLeaveHistory"

    # Body: {"EmployeeNumber": "<id>"}
    # Response.LeaveTypesList -> [ { ... } ]
    GET_LEAVE_TYPES = "getLeaveTypes"

    # --------------------------------------------------------------
    # Letters
    # --------------------------------------------------------------

    # Body: {"EmployeeNumber": "<id>"}
    # Response.ApplyLetterRequestDB -> [ { LetterType, Date, Status, Id } ]
    GET_LETTER_HISTORY = "getLetterHistory"

    # Body: {}
    # Response -> [ { ... } ]  (catalogue, not employee-specific)
    GET_LETTER_TYPES = "getLetterTypes"

    # --------------------------------------------------------------
    # Payroll
    # --------------------------------------------------------------

    # Body: {"EmployeeNumber": "<id>", "PayrollPeriod": "MMM-YYYY"}
    # Response -> base64 PDF of the payslip.
    #
    # NOT wired into the chatbot: the response is a whole payslip
    # document, far more than any question needs, and streaming it
    # into an LLM prompt would be a needless disclosure. Salary
    # questions are answered from the profile record and the app's
    # own Payslip screen is pointed to instead.
    USER_GET_PAY_SLIP_INFO = "userGetPaySlipInfo"


# Routes the chatbot is allowed to call, as an explicit allow-list.
# EjadahClient refuses anything outside this set.
READ_ONLY_ALLOW_LIST = frozenset(
    {
        EjadahRoute.GET_EMPLOYEE_INFO,
        EjadahRoute.GET_LEAVE_BALANCE,
        EjadahRoute.GET_LEAVE_HISTORY,
        EjadahRoute.GET_LEAVE_TYPES,
        EjadahRoute.GET_LETTER_HISTORY,
        EjadahRoute.GET_LETTER_TYPES,
    }
)


def is_allowed(route: str) -> bool:
    """
    True when the chatbot may call `route`.

    EJADAH_IDENTITY_ROUTE is admitted on top of the static list so a
    future token-introspection endpoint can be enabled by
    configuration without another release. It is still restricted to
    exactly the one name the operator configured.
    """

    from config.settings import settings

    if route in READ_ONLY_ALLOW_LIST:
        return True

    configured = (settings.ejadah_identity_route or "").strip()

    return bool(configured) and route == configured
