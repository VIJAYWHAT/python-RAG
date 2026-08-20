"""
Reads the authenticated employee's HR record from the Ejadah APIs.

Every method here takes a `Principal`, and the only employee number
it will ever send upstream is `principal.employee_id` - the value
that ejadah/identity_service.py verified. There is deliberately no
way to ask this service for "employee X's leave": the employee is
whoever the token belongs to.

Each call is made with the employee's OWN bearer token, so Ejadah's
own authorisation applies on top of ours. The service never holds a
token of its own and never reuses one caller's token for another.

The shapes below match what the Flutter app already consumes, so
the two stay in step:

    getEmployeeInfo   -> Response.EmployeeList[0]
                         { EMPLOYEENUMBER, EMPLOYEENAME, DEPARTMENT,
                           POS_SEG3, LINEMANAGER, NATIONALITY,
                           EMAIL_ADDRESS, EMP_PHONE_NUMBER, GENDER,
                           PASSPORTNO, PASSPORTEXPIRY, VISA_NO,
                           VISAEXPIRY, EMIRATESID,
                           EMIRATESIDEXPIRY, INSURANCE_NUMBER }

    getLeaveBalance   -> Response.LeaveBalance          (number)
    getLeaveHistory   -> Response.LeaveHistoryRecord    (list)
                         { ABSENCE_TYPE, START_DATE, END_DATE,
                           APPROVAL_STATUS, TRANSACTION_ID }
    getLetterHistory  -> Response.ApplyLetterRequestDB  (list)
                         { LetterType, Date, Status, Id }
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from config.settings import settings
from core.errors import AppError, AuthenticationError
from core.logging_config import get_logger, mask_employee
from core.ttl_cache import TTLCache
from ejadah.ejadah_client import EjadahClient, get_ejadah_client
from ejadah.ejadah_routes import EjadahRoute
from ejadah.identity_service import Principal


logger = get_logger(__name__)


# What a question can ask for. Kept as plain strings because the
# intent detector produces them.
TOPIC_PROFILE = "profile"
TOPIC_LEAVE_BALANCE = "leave_balance"
TOPIC_LEAVE_HISTORY = "leave_history"
TOPIC_SALARY = "salary"
TOPIC_LETTERS = "letters"
TOPIC_DOCUMENTS = "documents"

ALL_TOPICS = (
    TOPIC_PROFILE,
    TOPIC_LEAVE_BALANCE,
    TOPIC_LEAVE_HISTORY,
    TOPIC_SALARY,
    TOPIC_LETTERS,
    TOPIC_DOCUMENTS,
)


@dataclass
class EmployeeSnapshot:
    """
    What we managed to read for one employee, one question.

    `errors` records sections that failed so the prompt can say
    "that could not be retrieved" instead of the model inventing a
    number.
    """

    employee_id: str

    profile: Optional[Dict[str, Any]] = None

    leave_balance: Optional[float] = None

    leave_history: List[Dict[str, Any]] = field(default_factory=list)

    letters: List[Dict[str, Any]] = field(default_factory=list)

    errors: Dict[str, str] = field(default_factory=dict)

    @property
    def found(self) -> bool:

        return self.profile is not None


class EjadahEmployeeService:
    """
    Read-only view of one employee's HR record.

    Results are cached per (employee, section) for
    EMPLOYEE_CACHE_TTL_SECONDS - long enough that a three-question
    conversation does not hit the HR gateway nine times, short
    enough that an approval made during the conversation shows up.
    """

    def __init__(self, client: Optional[EjadahClient] = None) -> None:

        self._client = client or get_ejadah_client()

        self._cache = TTLCache(
            ttl_seconds=settings.employee_cache_ttl_seconds,
            max_entries=2000
        )

    # ==============================================================
    # Public API
    # ==============================================================

    def get_snapshot(
        self,
        principal: Principal,
        topics: Optional[List[str]] = None
    ) -> EmployeeSnapshot:
        """
        Fetches exactly the sections the question needs.

        Sections are fetched concurrently: a question like "how many
        leaves do I have left and what have I taken this month?"
        needs three upstream calls, and doing them in sequence adds
        a second of latency for no reason.
        """

        wanted = self._normalise_topics(topics)

        snapshot = EmployeeSnapshot(employee_id=principal.employee_id)

        # The profile is always loaded: the assistant needs to know
        # who it is speaking to, and it is where designation,
        # department and manager come from.
        tasks: Dict[str, Any] = {
            "profile": lambda: self.get_profile(principal)
        }

        if TOPIC_LEAVE_BALANCE in wanted or TOPIC_LEAVE_HISTORY in wanted:
            tasks["leave_balance"] = (
                lambda: self.get_leave_balance(principal)
            )

        if TOPIC_LEAVE_HISTORY in wanted:
            tasks["leave_history"] = (
                lambda: self.get_leave_history(principal)
            )

        if TOPIC_LETTERS in wanted:
            tasks["letters"] = lambda: self.get_letters(principal)

        auth_error: AuthenticationError | None = None

        with ThreadPoolExecutor(
            max_workers=min(4, len(tasks)),
            thread_name_prefix="ejadah-hr"
        ) as pool:

            futures = {
                pool.submit(function): name
                for name, function in tasks.items()
            }

            for future in as_completed(futures):

                name = futures[future]

                try:
                    value = future.result()

                except AuthenticationError as error:
                    # A dead token is not a partial failure - the
                    # whole request must fail so the app re-logs in.
                    auth_error = error

                except AppError as error:

                    logger.warning(
                        "HR section '%s' unavailable for employee=%s: %s",
                        name,
                        mask_employee(principal.employee_id),
                        error.detail or error.message
                    )

                    snapshot.errors[name] = error.message

                except Exception as error:  # pragma: no cover

                    logger.exception(
                        "HR section '%s' raised for employee=%s: %s",
                        name,
                        mask_employee(principal.employee_id),
                        error
                    )

                    snapshot.errors[name] = (
                        "This detail could not be retrieved."
                    )

                else:
                    setattr(snapshot, name, value)

        if auth_error is not None:
            raise auth_error

        return snapshot

    # --------------------------------------------------------------
    # Individual sections
    # --------------------------------------------------------------

    def get_profile(
        self,
        principal: Principal
    ) -> Optional[Dict[str, Any]]:

        def fetch() -> Optional[Dict[str, Any]]:

            response = self._client.post(
                EjadahRoute.GET_EMPLOYEE_INFO,
                token=principal.token,
                body={"EmployeeNumber": principal.employee_id}
            )

            rows = response.section("EmployeeList")

            record = _first_row(rows)

            if record is None:
                return None

            return self._guard_owner(principal, record)

        return self._cached(principal, "profile", fetch)

    def get_leave_balance(
        self,
        principal: Principal
    ) -> Optional[float]:

        def fetch() -> Optional[float]:

            response = self._client.post(
                EjadahRoute.GET_LEAVE_BALANCE,
                token=principal.token,
                # The Flutter app sends LeaveType: null to mean
                # "all types"; keep the payload identical.
                body={
                    "EmployeeId": principal.employee_id,
                    "LeaveType": None
                }
            )

            raw = response.section("LeaveBalance")

            if raw is None and not isinstance(response.payload, Mapping):
                raw = response.payload

            return _to_number(raw)

        return self._cached(principal, "leave_balance", fetch)

    def get_leave_history(
        self,
        principal: Principal
    ) -> List[Dict[str, Any]]:

        def fetch() -> List[Dict[str, Any]]:

            response = self._client.post(
                EjadahRoute.GET_LEAVE_HISTORY,
                token=principal.token,
                body={"EmployeeNumber": principal.employee_id}
            )

            rows = response.section("LeaveHistoryRecord") or []

            if isinstance(rows, Mapping):
                rows = [rows]

            return [
                dict(row)
                for row in rows
                if isinstance(row, Mapping)
            ]

        return self._cached(principal, "leave_history", fetch) or []

    def get_letters(
        self,
        principal: Principal
    ) -> List[Dict[str, Any]]:

        def fetch() -> List[Dict[str, Any]]:

            response = self._client.post(
                EjadahRoute.GET_LETTER_HISTORY,
                token=principal.token,
                body={"EmployeeNumber": principal.employee_id}
            )

            rows = response.section("ApplyLetterRequestDB") or []

            if isinstance(rows, Mapping):
                rows = [rows]

            return [
                dict(row)
                for row in rows
                if isinstance(row, Mapping)
            ]

        return self._cached(principal, "letters", fetch) or []

    # --------------------------------------------------------------
    # Cache control
    # --------------------------------------------------------------

    def invalidate(self, employee_id: str) -> int:

        return self._cache.invalidate_matching(
            lambda key, _value: (
                isinstance(key, tuple)
                and key
                and str(key[0]).casefold()
                == str(employee_id).strip().casefold()
            )
        )

    # ==============================================================
    # Internals
    # ==============================================================

    @staticmethod
    def _normalise_topics(topics: Optional[List[str]]) -> set[str]:

        if not topics:
            return {TOPIC_PROFILE}

        if isinstance(topics, str):
            topics = [topics]

        wanted = {
            str(topic).strip().lower()
            for topic in topics
            if topic
        }

        return wanted or {TOPIC_PROFILE}

    def _cached(self, principal: Principal, section: str, fetch):

        key = (principal.employee_id.casefold(), section)

        cached = self._cache.get(key)

        if cached is not None:
            return cached

        value = fetch()

        # Cache empty lists too, otherwise an employee with no leave
        # history re-queries the gateway on every message. `None`
        # (a genuine failure) is not cached.
        if value is not None:
            self._cache.set(key, value)

        return value

    @staticmethod
    def _guard_owner(
        principal: Principal,
        record: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Last-mile check: refuse to hand back a record that is not
        the caller's, whatever the upstream returned.

        This is the belt to identity_service.py's braces. If a
        gateway bug or a mis-scoped query ever returned someone
        else's row, it stops here rather than reaching a prompt.
        """

        row_id = None

        for key in (
            "EMPLOYEENUMBER",
            "EmployeeNumber",
            "EMPLOYEEID",
            "EmployeeId",
        ):

            value = record.get(key)

            if value is not None and str(value).strip():
                row_id = str(value).strip()
                break

        if row_id is None:
            # No identifier to check against; the row is whatever
            # the employee's own token returned.
            return record

        if row_id.casefold() != principal.employee_id.casefold():

            logger.error(
                "SECURITY: Ejadah returned employee=%s for a request "
                "authenticated as employee=%s. Record discarded.",
                mask_employee(row_id),
                mask_employee(principal.employee_id)
            )

            raise AppError(
                "Your employee record could not be verified. "
                "Please contact HR.",
                detail=(
                    f"Owner mismatch: row={row_id} "
                    f"principal={principal.employee_id}"
                )
            )

        return record


# ==================================================================
# Helpers
# ==================================================================


def _first_row(rows) -> Optional[Dict[str, Any]]:

    if rows is None:
        return None

    if isinstance(rows, Mapping):
        return dict(rows)

    if isinstance(rows, list) and rows:

        first = rows[0]

        if isinstance(first, Mapping):
            return dict(first)

    return None


def _to_number(value) -> Optional[float]:

    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    if not text or text.lower() in ("null", "none"):
        return None

    try:
        return float(text)

    except ValueError:
        return None


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_service: EjadahEmployeeService | None = None
_service_lock = threading.Lock()


def get_employee_service() -> EjadahEmployeeService:

    global _service

    if _service is None:

        with _service_lock:

            if _service is None:
                _service = EjadahEmployeeService()

    return _service
