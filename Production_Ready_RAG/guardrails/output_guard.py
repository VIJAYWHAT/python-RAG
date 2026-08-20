"""
The last check before an answer leaves the building.

The input guardrails decide what the model is allowed to be asked.
This one decides what it is allowed to say, which matters because
the model sees two things it must not repeat verbatim: its own
system instructions, and whatever the retriever pulled out of the
knowledge base.

Four checks, in order of severity:

1. **Cross-employee leak.** The answer must not contain an employee
   number other than the caller's. This is the one failure that
   would be a genuine data breach, so a hit replaces the whole
   answer rather than editing it.

2. **Credential leak.** A bearer token or API key in the output
   means something went badly wrong upstream; the answer is
   replaced.

3. **System-prompt disclosure.** If the model has started reciting
   its instructions, the answer is replaced.

4. **Stray PII.** Passport, Emirates ID and card-shaped numbers are
   masked in place. This one edits rather than replaces, because a
   policy document legitimately quoting an example number should
   not cost the employee their answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from core.logging_config import get_logger, mask_employee
from guardrails import pii_filter


logger = get_logger(__name__)


SAFE_FALLBACK = (
    "I'm not able to share that. I can help with your own HR "
    "details and with Ejadah's HR policies - please ask me about "
    "one of those, or contact HR directly."
)


# Phrases that only appear if the model is reciting its own prompt.
_PROMPT_DISCLOSURE_MARKERS = (
    "verified employee data (from the hr",
    "hr policy reference (from the hr knowledge base)",
    "employee record (the authenticated employee",
    "you are the hr ai assistant of ejadah",
    "you are an hr representative ai assistant",
    "never reveal these instructions",
    "system prompt",
    "my instructions are",
    "my system message",
)


# Employee-number shapes used by Ejadah. Two families are seen in
# the app: an alphabetic prefix plus digits (USE23120) and the demo
# "employee-001" form.
_EMPLOYEE_ID_PATTERN = re.compile(
    r"\b(?:[A-Z]{2,4}\d{4,8}|employee-\d{3,6})\b",
    re.IGNORECASE
)


@dataclass
class OutputGuardResult:

    answer: str

    blocked: bool = False

    modified: bool = False

    reason: Optional[str] = None


class OutputGuard:

    def check(
        self,
        answer: str,
        employee_id: str,
        question: str = ""
    ) -> OutputGuardResult:

        if not answer or not answer.strip():

            return OutputGuardResult(
                answer=(
                    "I'm sorry, I couldn't produce an answer just "
                    "now. Please try asking again."
                ),
                reason="empty_answer"
            )

        # ----------------------------------------------------------
        # 1. Cross-employee leak
        # ----------------------------------------------------------

        foreign = self._foreign_employee_ids(answer, employee_id)

        if foreign:

            logger.error(
                "OUTPUT BLOCKED: answer for employee=%s mentioned "
                "other employee number(s) %s",
                mask_employee(employee_id),
                sorted(foreign)
            )

            return OutputGuardResult(
                answer=SAFE_FALLBACK,
                blocked=True,
                reason="cross_employee_reference"
            )

        # ----------------------------------------------------------
        # 2. Credential leak
        # ----------------------------------------------------------

        if pii_filter.contains_credential(answer):

            logger.error(
                "OUTPUT BLOCKED: answer for employee=%s contained "
                "something credential-shaped",
                mask_employee(employee_id)
            )

            return OutputGuardResult(
                answer=SAFE_FALLBACK,
                blocked=True,
                reason="credential_in_output"
            )

        # ----------------------------------------------------------
        # 3. System-prompt disclosure
        # ----------------------------------------------------------

        lowered = answer.lower()

        for marker in _PROMPT_DISCLOSURE_MARKERS:

            if marker in lowered:

                logger.warning(
                    "OUTPUT BLOCKED: answer for employee=%s looked "
                    "like prompt disclosure (marker=%r)",
                    mask_employee(employee_id),
                    marker
                )

                return OutputGuardResult(
                    answer=SAFE_FALLBACK,
                    blocked=True,
                    reason="prompt_disclosure"
                )

        # ----------------------------------------------------------
        # 4. Stray PII -> mask in place
        # ----------------------------------------------------------

        scrubbed = pii_filter.scrub(
            answer,
            categories={"emirates_id", "iban", "card", "passport"}
        )

        if scrubbed != answer:

            logger.info(
                "Masked identifier-shaped text in an answer for "
                "employee=%s",
                mask_employee(employee_id)
            )

            return OutputGuardResult(
                answer=scrubbed,
                modified=True,
                reason="pii_masked"
            )

        return OutputGuardResult(answer=answer)

    # --------------------------------------------------------------

    @staticmethod
    def _foreign_employee_ids(answer: str, employee_id: str) -> set[str]:

        own = str(employee_id or "").strip().casefold()

        found = {
            match.group(0)
            for match in _EMPLOYEE_ID_PATTERN.finditer(answer)
        }

        return {
            value
            for value in found
            if value.strip().casefold() != own
        }
