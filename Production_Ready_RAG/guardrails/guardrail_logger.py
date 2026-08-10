import logging
import os


class GuardrailLogger:

    def __init__(
        self,
        log_file: str = "logs/guardrails.log"
    ):

        os.makedirs(
            os.path.dirname(log_file),
            exist_ok=True
        )

        self.logger = logging.getLogger(
            "guardrail"
        )

        self.logger.setLevel(
            logging.INFO
        )

        if not self.logger.handlers:

            handler = logging.FileHandler(
                log_file,
                encoding="utf-8"
            )

            formatter = logging.Formatter(
                "%(asctime)s | %(message)s"
            )

            handler.setFormatter(
                formatter
            )

            self.logger.addHandler(
                handler
            )

    def log_blocked(
        self,
        question: str,
        reason: str
    ):

        self.logger.warning(
            "BLOCKED | "
            f"Question={question} | "
            f"Reason={reason}"
        )

    def log_out_of_scope(
        self,
        question: str,
        reason: str
    ):

        self.logger.warning(
            "OUT_OF_SCOPE | "
            f"Question={question} | "
            f"Reason={reason}"
        )