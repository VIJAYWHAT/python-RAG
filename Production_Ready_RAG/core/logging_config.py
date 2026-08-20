"""
Logging setup.

Every module uses `get_logger(__name__)` instead of print(), so the
whole service can be shipped to a log aggregator and so that
employee data never lands in stdout by accident.

Two things matter for an HR assistant:

1. The question and the answer are personal data. They are logged
   only when DEBUG is on, and DEBUG is refused in production.
2. Tokens must never reach the log file, so `mask_token` is used
   everywhere a token would otherwise be printed.
"""

import logging
import logging.handlers
import os
import sys

from config.settings import settings


_CONFIGURED = False


class _RedactFilter(logging.Filter):
    """
    Last line of defence: drops anything that looks like a bearer
    token out of a formatted message.
    """

    SENSITIVE_KEYS = (
        "authorization",
        "accesstoken",
        "access_token",
        "bearer ",
    )

    def filter(self, record: logging.LogRecord) -> bool:

        try:
            message = record.getMessage()

        except Exception:
            return True

        lowered = message.lower()

        if not any(key in lowered for key in self.SENSITIVE_KEYS):
            return True

        # Rebuild the record with a redacted message. Args are
        # already merged into `message`, so clear them.
        record.msg = _redact(message)
        record.args = ()

        return True


def _redact(message: str) -> str:

    import re

    patterns = [
        (r"(?i)(bearer\s+)([A-Za-z0-9\.\-_=]{8,})", r"\1<redacted>"),
        (
            r"(?i)(\"?(?:access_?token|authorization)\"?\s*[:=]\s*\"?)"
            r"([A-Za-z0-9\.\-_=]{8,})",
            r"\1<redacted>"
        ),
    ]

    for pattern, replacement in patterns:
        message = re.sub(pattern, replacement, message)

    return message


def configure_logging() -> None:

    global _CONFIGURED

    if _CONFIGURED:
        return

    level = getattr(
        logging,
        settings.log_level.strip().upper(),
        logging.INFO
    )

    formatter = logging.Formatter(
        fmt=(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        ),
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    redactor = _RedactFilter()

    handlers: list[logging.Handler] = []

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(redactor)
    handlers.append(stream_handler)

    if settings.log_file:

        directory = os.path.dirname(settings.log_file)

        if directory:
            os.makedirs(directory, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            settings.log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(redactor)
        handlers.append(file_handler)

    root = logging.getLogger()

    # Uvicorn installs its own handlers; replace ours cleanly on
    # reload so messages are not duplicated.
    for existing in list(root.handlers):
        root.removeHandler(existing)

    for handler in handlers:
        root.addHandler(handler)

    root.setLevel(level)

    # Third-party noise.
    for noisy in (
        "httpx",
        "httpcore",
        "urllib3",
        "engineio",
        "socketio",
        "chromadb",
        "sentence_transformers",
        "openai",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:

    configure_logging()

    return logging.getLogger(name)


# ==================================================================
# Helpers for safe logging
# ==================================================================


def mask_token(token: str | None) -> str:
    """
    Renders a token as `abcd...wxyz (len=214)` so that two log lines
    can be correlated without the token itself being recoverable.
    """

    if not token:
        return "<none>"

    token = token.strip()

    if len(token) <= 10:
        return f"<short token len={len(token)}>"

    return f"{token[:4]}...{token[-4:]} (len={len(token)})"


def mask_employee(employee_id: str | None) -> str:
    """
    Employee numbers are pseudonymous identifiers, not secrets, and
    we need them to trace a complaint back to a conversation. They
    are logged in full but routed through this helper so the policy
    can be changed in one place.
    """

    return employee_id or "<unknown>"


def log_personal(logger, message: str, *args) -> None:
    """
    Logs message content (questions, answers, employee records)
    only when DEBUG is explicitly enabled.
    """

    if settings.debug:
        logger.debug(message, *args)
