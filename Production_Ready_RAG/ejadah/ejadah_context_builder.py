"""
Turns one employee's Ejadah record into the text block that goes
into the LLM prompt.

Two principles drive everything here:

**Data minimisation.** Only the sections the question actually
touches are included. A question about the leave policy does not
put the employee's passport number in front of a model, and a
question about the department does not put their salary there
either. Personal documents and pay are gated behind an explicit
ask.

**No invention.** When a section failed to load, the block says so
in words. That is the difference between "your remaining balance is
not available right now" and the model guessing a number.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional

from core.logging_config import get_logger
from ejadah.employee_service import (
    TOPIC_DOCUMENTS,
    TOPIC_LEAVE_BALANCE,
    TOPIC_LEAVE_HISTORY,
    TOPIC_LETTERS,
    TOPIC_SALARY,
    EmployeeSnapshot,
)


logger = get_logger(__name__)


# Values Oracle-backed APIs use for "nothing here".
_EMPTY_VALUES = {"", "null", "none", "n/a", "na", "-"}

_NOT_AVAILABLE = "Not available"


# Date formats seen coming out of the Ejadah / Oracle HCM stack.
_DATE_FORMATS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%d-%b-%Y",
    "%d-%B-%Y",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%b %d, %Y",
)


class EjadahContextBuilder:

    # ==============================================================
    # Public API
    # ==============================================================

    def build(
        self,
        snapshot: EmployeeSnapshot,
        topics: Optional[Iterable[str]] = None
    ) -> Dict[str, Any]:
        """
        Returns:
            {
              "found": bool,
              "text":  "<block for the prompt>",
              "sections": ["profile", "leave_balance", ...]
            }
        """

        wanted = {
            str(topic).strip().lower()
            for topic in (topics or [])
            if topic
        }

        if not snapshot.found:

            return {
                "found": False,
                "text": "",
                "sections": []
            }

        blocks: List[str] = []
        sections: List[str] = []

        # ----------------------------------------------------------
        # Identity - always present so the assistant knows who it is
        # talking to, but salary and documents stay out unless asked.
        # ----------------------------------------------------------

        blocks.append(
            self._format_profile(
                snapshot.profile or {},
                include_salary=TOPIC_SALARY in wanted,
                include_documents=TOPIC_DOCUMENTS in wanted
            )
        )
        sections.append("profile")

        # ----------------------------------------------------------
        # Leave balance
        # ----------------------------------------------------------

        if TOPIC_LEAVE_BALANCE in wanted or TOPIC_LEAVE_HISTORY in wanted:

            blocks.append(
                self._format_leave_balance(
                    snapshot.leave_balance,
                    error=snapshot.errors.get("leave_balance")
                )
            )
            sections.append("leave_balance")

        # ----------------------------------------------------------
        # Leave history
        # ----------------------------------------------------------

        if TOPIC_LEAVE_HISTORY in wanted:

            blocks.append(
                self._format_leave_history(
                    snapshot.leave_history,
                    error=snapshot.errors.get("leave_history")
                )
            )
            sections.append("leave_history")

        # ----------------------------------------------------------
        # Letter requests
        # ----------------------------------------------------------

        if TOPIC_LETTERS in wanted:

            blocks.append(
                self._format_letters(
                    snapshot.letters,
                    error=snapshot.errors.get("letters")
                )
            )
            sections.append("letters")

        # ----------------------------------------------------------
        # Salary: the app has a dedicated payslip download, and the
        # HR API returns a whole PDF rather than figures, so we say
        # where to look instead of feeding a document to the model.
        # ----------------------------------------------------------

        if TOPIC_SALARY in wanted:

            blocks.append(self._format_salary_guidance(snapshot))
            sections.append("salary")

        text = "\n\n".join(block for block in blocks if block)

        return {
            "found": True,
            "text": text,
            "sections": sections
        }

    # ==============================================================
    # Profile
    # ==============================================================

    def _format_profile(
        self,
        profile: Dict[str, Any],
        include_salary: bool = False,
        include_documents: bool = False
    ) -> str:

        lines = [
            "EMPLOYEE RECORD (the authenticated employee who is asking):",
            self._row("Employee Number", profile, "EMPLOYEENUMBER"),
            self._row("Full Name", profile, "EMPLOYEENAME"),
            self._row("Designation", profile, "POS_SEG3", "DESIGNATION"),
            self._row("Department", profile, "DEPARTMENT"),
            self._row("Reporting Manager", profile, "LINEMANAGER"),
            self._row("Work Email", profile, "EMAIL_ADDRESS"),
            self._row("Contact Number", profile, "EMP_PHONE_NUMBER"),
            self._row("Nationality", profile, "NATIONALITY"),
            self._row("Gender", profile, "GENDER"),
        ]

        joined = self._first(
            profile,
            "DATE_OF_JOINING",
            "HIRE_DATE",
            "DATEOFJOIN",
            "JOIN_DATE"
        )

        if joined:

            lines.append(f"- Date of Joining : {self._as_date_text(joined)}")

            tenure = self._tenure_text(joined)

            if tenure:
                lines.append(f"- Tenure          : {tenure}")

        grade = self._first(profile, "GRADE", "EMP_GRADE")

        if grade:
            lines.append(f"- Grade           : {grade}")

        entity = self._first(profile, "ENTITY", "COMPANY", "BUSINESS_GROUP")

        if entity:
            lines.append(f"- Entity          : {entity}")

        # ----------------------------------------------------------
        # Personal documents: only when the employee asked about
        # them. Expiry dates are the useful part of the answer, so
        # the numbers are trimmed to their last four characters.
        # ----------------------------------------------------------

        if include_documents:

            lines.append("")
            lines.append("PERSONAL DOCUMENTS:")

            lines.append(
                "- Passport      : "
                f"{self._masked(profile, 'PASSPORTNO')} "
                f"(expires {self._as_date_text(profile.get('PASSPORTEXPIRY'))})"
            )

            lines.append(
                "- Visa          : "
                f"{self._masked(profile, 'VISA_NO')} "
                f"(expires {self._as_date_text(profile.get('VISAEXPIRY'))})"
            )

            lines.append(
                "- Emirates ID   : "
                f"{self._masked(profile, 'EMIRATESID')} "
                "(expires "
                f"{self._as_date_text(profile.get('EMIRATESIDEXPIRY'))})"
            )

            lines.append(
                "  Note: document numbers are shown partially masked. "
                "Tell the employee the full number is on the Personal "
                "Documents screen in the app."
            )

        if include_salary:

            # The Ejadah profile response carries no pay figures, so
            # say nothing rather than implying one exists.
            basic = self._first(
                profile,
                "BASIC_SALARY",
                "BASICSALARY",
                "SALARY"
            )

            if basic:
                lines.append(f"- Basic Salary    : {basic}")

        return "\n".join(line for line in lines if line is not None)

    # ==============================================================
    # Leave balance
    # ==============================================================

    def _format_leave_balance(
        self,
        balance: Optional[float],
        error: Optional[str] = None
    ) -> str:

        header = f"LEAVE BALANCE (as on {self._today_text()}):"

        if error:

            return (
                f"{header}\n"
                f"Could not be retrieved from the HR system just now. "
                f"Do NOT state a number - tell the employee to try "
                f"again shortly or to check the Leave screen in the app."
            )

        if balance is None:

            return (
                f"{header}\n"
                f"The HR system returned no leave balance for this "
                f"employee. Do NOT state a number."
            )

        return (
            f"{header}\n"
            f"- Remaining leave balance: {self._number_text(balance)} day(s)\n"
            f"This is the total remaining entitlement across leave "
            f"types, exactly as returned by the HR system."
        )

    # ==============================================================
    # Leave history
    # ==============================================================

    def _format_leave_history(
        self,
        history: List[Dict[str, Any]],
        error: Optional[str] = None
    ) -> str:

        header = "LEAVE HISTORY:"

        if error:

            return (
                f"{header}\n"
                f"Could not be retrieved from the HR system just now. "
                f"Do NOT list or count any leave - tell the employee "
                f"to try again shortly."
            )

        if not history:

            return (
                f"{header}\n"
                f"The HR system returned no leave records for this "
                f"employee."
            )

        rows = [self._normalise_leave_row(row) for row in history]

        rows = [row for row in rows if row is not None]

        if not rows:
            return f"{header}\nNo readable leave records were returned."

        today = date.today()

        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)

        this_week = [
            row for row in rows
            if self._overlaps(row, week_start, week_end)
        ]

        this_month = [
            row for row in rows
            if row["start"] and row["start"].year == today.year
            and row["start"].month == today.month
        ]

        upcoming = [
            row for row in rows
            if row["start"] and row["start"] > today
        ]

        approved_this_year = [
            row for row in rows
            if row["start"]
            and row["start"].year == today.year
            and "approve" in row["status"].lower()
        ]

        pending = [
            row for row in rows
            if "pend" in row["status"].lower()
        ]

        blocks = [header]

        blocks.append(
            self._leave_table(
                f"Leave this week ({week_start.isoformat()} to "
                f"{week_end.isoformat()})",
                this_week,
                "No leave falls in the current week."
            )
        )

        blocks.append(
            self._leave_table(
                f"Leave this month ({today.strftime('%B %Y')})",
                this_month,
                "No leave recorded for the current month."
            )
        )

        if upcoming:
            blocks.append(
                self._leave_table(
                    "Upcoming leave",
                    upcoming,
                    "No upcoming leave."
                )
            )

        if pending:
            blocks.append(
                self._leave_table(
                    "Pending approval",
                    pending,
                    "Nothing pending."
                )
            )

        total_days = sum(
            row["days"] or 0
            for row in approved_this_year
        )

        blocks.append(
            f"Approved leave days taken in {today.year}: "
            f"{self._number_text(total_days)} day(s) across "
            f"{len(approved_this_year)} request(s)."
        )

        blocks.append(
            self._leave_table(
                "Full leave history returned by the HR system",
                rows[:40],
                "No records."
            )
        )

        if len(rows) > 40:
            blocks.append(
                f"(Only the {min(40, len(rows))} most recent of "
                f"{len(rows)} records are listed above.)"
            )

        return "\n\n".join(blocks)

    def _leave_table(
        self,
        title: str,
        rows: List[Dict[str, Any]],
        empty_text: str
    ) -> str:

        if not rows:
            return f"{title}: {empty_text}"

        lines = [f"{title}:"]

        for row in rows:

            start = (
                row["start"].isoformat()
                if row["start"]
                else _NOT_AVAILABLE
            )

            end = (
                row["end"].isoformat()
                if row["end"]
                else start
            )

            days = (
                f"{self._number_text(row['days'])} day(s)"
                if row["days"] is not None
                else ""
            )

            parts = [
                row["type"] or "Leave",
                f"{start} to {end}" if end != start else start,
                days,
                f"Status: {row['status'] or _NOT_AVAILABLE}",
            ]

            lines.append(
                "- " + " | ".join(part for part in parts if part)
            )

        return "\n".join(lines)

    def _normalise_leave_row(
        self,
        row: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:

        if not isinstance(row, dict):
            return None

        start = self._as_date(
            self._first(
                row,
                "START_DATE",
                "StartDate",
                "FROM_DATE",
                "LEAVE_DATE"
            )
        )

        end = self._as_date(
            self._first(row, "END_DATE", "EndDate", "TO_DATE")
        )

        days = self._as_number(
            self._first(
                row,
                "ABSENCE_DAYS",
                "AbsenceDays",
                "DAYS",
                "NO_OF_DAYS"
            )
        )

        if days is None and start and end:
            days = float((end - start).days + 1)

        return {
            "type": self._text(
                self._first(
                    row,
                    "ABSENCE_TYPE",
                    "AbsenceType",
                    "LEAVE_TYPE",
                    "ABSENCE_CATEGORY"
                )
            ),
            "start": start,
            "end": end or start,
            "days": days,
            "status": self._text(
                self._first(
                    row,
                    "APPROVAL_STATUS",
                    "ApprovalStatus",
                    "STATUS"
                )
            ) or "",
        }

    @staticmethod
    def _overlaps(
        row: Dict[str, Any],
        window_start: date,
        window_end: date
    ) -> bool:

        start = row.get("start")
        end = row.get("end") or start

        if start is None:
            return False

        return start <= window_end and end >= window_start

    # ==============================================================
    # Letters
    # ==============================================================

    def _format_letters(
        self,
        letters: List[Dict[str, Any]],
        error: Optional[str] = None
    ) -> str:

        header = "LETTER REQUESTS:"

        if error:

            return (
                f"{header}\n"
                f"Could not be retrieved just now. Do NOT list any "
                f"letter requests - tell the employee to try again "
                f"shortly or to open the Letter screen in the app."
            )

        if not letters:

            return (
                f"{header}\n"
                f"The HR system returned no letter requests for this "
                f"employee."
            )

        lines = [header]

        for row in letters[:25]:

            parts = [
                self._text(
                    self._first(row, "LetterType", "LETTERTYPE", "Type")
                ) or "Letter",
                self._as_date_text(
                    self._first(row, "Date", "RequestDate", "CREATED_ON")
                ),
                "Status: "
                + (
                    self._text(self._first(row, "Status", "STATUS"))
                    or _NOT_AVAILABLE
                ),
            ]

            lines.append("- " + " | ".join(part for part in parts if part))

        if len(letters) > 25:
            lines.append(
                f"(Showing the 25 most recent of {len(letters)} "
                f"requests.)"
            )

        return "\n".join(lines)

    # ==============================================================
    # Salary
    # ==============================================================

    @staticmethod
    def _format_salary_guidance(snapshot: EmployeeSnapshot) -> str:

        return (
            "SALARY AND PAYSLIP:\n"
            "Pay figures are NOT available to this assistant. The HR "
            "system exposes payslips only as a downloadable document, "
            "and this assistant deliberately does not read them.\n"
            "If the employee asks about salary, pay, CTC, increments "
            "or a payslip: say clearly that you cannot see pay "
            "details, and direct them to Services > Payslip in the "
            "app to download the payslip for a chosen month, or to HR "
            "for anything the payslip does not answer. NEVER state, "
            "estimate or guess an amount."
        )

    # ==============================================================
    # Small helpers
    # ==============================================================

    def _row(
        self,
        label: str,
        source: Dict[str, Any],
        *keys: str
    ) -> str:

        value = self._first(source, *keys)

        padded = f"{label:<18}"

        return f"- {padded}: {value if value else _NOT_AVAILABLE}"

    @staticmethod
    def _first(source: Dict[str, Any], *keys: str):

        if not isinstance(source, dict):
            return None

        for key in keys:

            if key not in source:
                continue

            value = source.get(key)

            if value is None:
                continue

            text = str(value).strip()

            if text.lower() in _EMPTY_VALUES:
                continue

            return text

        return None

    @staticmethod
    def _text(value) -> Optional[str]:

        if value is None:
            return None

        text = str(value).strip()

        return None if text.lower() in _EMPTY_VALUES else text

    @staticmethod
    def _as_number(value) -> Optional[float]:

        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        text = str(value).strip()

        if not text or text.lower() in _EMPTY_VALUES:
            return None

        try:
            return float(text)

        except ValueError:
            return None

    @staticmethod
    def _number_text(value) -> str:

        if value is None:
            return _NOT_AVAILABLE

        try:
            number = float(value)

        except (TypeError, ValueError):
            return str(value)

        if number == int(number):
            return str(int(number))

        return f"{number:.1f}"

    @classmethod
    def _as_date(cls, value) -> Optional[date]:

        if value is None:
            return None

        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        text = str(value).strip()

        if not text or text.lower() in _EMPTY_VALUES:
            return None

        # Trim a trailing zone/fraction the formats below do not
        # cover, e.g. 2025-08-19T00:00:00.000+04:00
        candidate = text.replace("Z", "")

        for separator in (".", "+"):

            if separator in candidate and "T" in candidate:
                candidate = candidate.split(separator)[0]

        for fmt in _DATE_FORMATS:

            try:
                return datetime.strptime(candidate, fmt).date()

            except ValueError:
                continue

        try:
            return datetime.fromisoformat(candidate).date()

        except ValueError:
            logger.debug("Unparseable date from Ejadah: %r", text)
            return None

    @classmethod
    def _as_date_text(cls, value) -> str:

        parsed = cls._as_date(value)

        if parsed:
            return parsed.strftime("%d %B %Y")

        text = cls._text(value)

        return text or _NOT_AVAILABLE

    @classmethod
    def _masked(cls, source: Dict[str, Any], key: str) -> str:
        """
        `A1234567` -> `****4567`.

        The employee already knows their own document number, so the
        useful part of the answer is the expiry date. Showing only
        the last four keeps the number out of prompts, logs and any
        model provider's request history.
        """

        value = cls._first(source, key)

        if not value:
            return _NOT_AVAILABLE

        text = str(value)

        if len(text) <= 4:
            return "*" * len(text)

        return "*" * (len(text) - 4) + text[-4:]

    @staticmethod
    def _today_text() -> str:

        return date.today().strftime("%d %B %Y")

    @classmethod
    def _tenure_text(cls, joined) -> Optional[str]:

        start = cls._as_date(joined)

        if start is None:
            return None

        days = (date.today() - start).days

        if days < 0:
            return None

        years = days // 365
        months = (days % 365) // 30

        if years and months:
            return f"{years} year(s) {months} month(s)"

        if years:
            return f"{years} year(s)"

        return f"{months} month(s)"
