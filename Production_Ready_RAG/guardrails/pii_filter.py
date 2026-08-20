"""
Scrubs identifiers out of text.

Used in two directions:

* **Outbound** - a last pass over the model's answer, in case a
  retrieved policy document or a stray prompt fragment carried
  somebody's ID number into the reply.

* **Logging** - so an operator reading logs to debug a conversation
  does not accumulate a file of Emirates ID numbers.

The employee's own contact details are deliberately NOT scrubbed on
the outbound path: "what is my registered mobile number?" is a
legitimate question and the answer is their own data. Only patterns
that identify a *person* in a way the employee should not be
collecting - national ID, passport, bank account, card numbers -
are masked, plus anything that looks like a credential.
"""

from __future__ import annotations

import re
from typing import Iterable, Tuple


# ------------------------------------------------------------------
# Patterns
# ------------------------------------------------------------------
#
# Each entry: (name, compiled pattern, replacement builder)
#
# Ordering matters: the more specific formats run first so that a
# UAE Emirates ID is not partly eaten by the generic long-number
# rule.
# ------------------------------------------------------------------

def _keep_last(match: re.Match, keep: int = 4) -> str:

    text = match.group(0)

    digits_only = re.sub(r"\D", "", text)

    if len(digits_only) <= keep:
        return "*" * len(text)

    return "*" * (len(text) - keep) + text[-keep:]


_PATTERNS: Tuple[Tuple[str, re.Pattern, object], ...] = (

    # Bearer tokens / API keys. Always fully removed.
    (
        "credential",
        re.compile(
            r"(?i)\b(?:bearer\s+[A-Za-z0-9._\-]{12,}"
            r"|gsk_[A-Za-z0-9]{20,}"
            r"|sk-[A-Za-z0-9]{20,}"
            r"|sess-[A-Za-z0-9._\-]{12,})",
        ),
        lambda match: "[redacted credential]",
    ),

    # UAE Emirates ID: 784-YYYY-NNNNNNN-C
    (
        "emirates_id",
        re.compile(r"\b784[-\s]?\d{4}[-\s]?\d{7}[-\s]?\d\b"),
        _keep_last,
    ),

    # IBAN
    (
        "iban",
        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
        _keep_last,
    ),

    # Payment card
    (
        "card",
        re.compile(r"\b(?:\d[ -]?){13,19}\b"),
        _keep_last,
    ),

    # Passport: one or two letters then 6-8 digits
    (
        "passport",
        re.compile(r"\b[A-Z]{1,2}\d{6,8}\b"),
        _keep_last,
    ),
)


def scrub(text: str, categories: Iterable[str] | None = None) -> str:
    """
    Masks identifiers in `text`.

    `categories` limits which patterns run; the default runs all of
    them.
    """

    if not text:
        return text

    wanted = set(categories) if categories else None

    result = text

    for name, pattern, replacement in _PATTERNS:

        if wanted is not None and name not in wanted:
            continue

        result = pattern.sub(replacement, result)

    return result


def scrub_credentials(text: str) -> str:
    """Credentials only - safe to run on anything, including logs."""

    return scrub(text, categories={"credential"})


def contains_credential(text: str) -> bool:

    if not text:
        return False

    for name, pattern, _ in _PATTERNS:

        if name == "credential" and pattern.search(text):
            return True

    return False
