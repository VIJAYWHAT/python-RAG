from dataclasses import dataclass
from enum import Enum


class GuardrailStatus(Enum):
    ALLOW = "allow"
    BLOCKED = "blocked"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass
class GuardrailResult:

    status: GuardrailStatus

    reason: str = ""

    message: str = ""