"""
Chat session identifiers.

A "session" here is one conversation thread, not a login. The
Flutter app generates the id and keeps it so a conversation survives
the screen being closed; the backend uses it to look up history.

Because the id comes from the client it is treated as untrusted
input, and two rules apply:

1. **It is validated.** A session id is a short opaque string. It
   ends up in a SQLite lookup and in log lines, so its shape is
   pinned rather than trusted.

2. **It is scoped to the employee.** Every read and write of
   conversation memory uses `scope()`, which prefixes the verified
   employee number. Two employees who happen to generate the same
   session id therefore cannot see each other's messages, and a
   client that guesses another employee's session id gets its own
   empty thread.
"""

from __future__ import annotations

import re
import uuid

from core.errors import ValidationError


# Deliberately narrow: letters, digits, dash, underscore, colon.
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-:]{1,100}$")

_DEFAULT_PREFIX = "chat"


class SessionManager:

    MAX_LENGTH = 100

    # --------------------------------------------------------------

    @staticmethod
    def new_session_id(prefix: str = _DEFAULT_PREFIX) -> str:

        return f"{prefix}-{uuid.uuid4().hex}"

    # --------------------------------------------------------------

    @classmethod
    def validate(cls, session_id: str | None) -> str:
        """
        Returns a clean session id, or raises ValidationError.

        An empty value is replaced with a fresh id rather than
        rejected: a first message with no session yet is normal.
        """

        if session_id is None:
            return cls.new_session_id()

        candidate = str(session_id).strip()

        if not candidate:
            return cls.new_session_id()

        if len(candidate) > cls.MAX_LENGTH:

            raise ValidationError(
                "That chat session could not be used. "
                "Please start a new chat.",
                detail=f"session_id too long ({len(candidate)} chars)"
            )

        if not _SESSION_ID_PATTERN.match(candidate):

            raise ValidationError(
                "That chat session could not be used. "
                "Please start a new chat.",
                detail=f"session_id has invalid characters: {candidate!r}"
            )

        return candidate

    # --------------------------------------------------------------

    @staticmethod
    def scope(employee_id: str, session_id: str) -> str:
        """
        The key conversation memory is actually stored under.

        Always derived from the VERIFIED employee number, so a
        client cannot reach another employee's thread by sending
        their session id.
        """

        if not employee_id:
            raise ValidationError(detail="Cannot scope a session with no employee")

        return f"{employee_id.strip().casefold()}::{session_id}"

    # --------------------------------------------------------------
    # Backwards-compatible alias
    # --------------------------------------------------------------

    @classmethod
    def get_scoped_session_id(
        cls,
        user_id: str,
        session_id: str
    ) -> str:

        return cls.scope(user_id, cls.validate(session_id))
