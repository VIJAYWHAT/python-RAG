from dataclasses import dataclass
from datetime import datetime


@dataclass
class HRQuery:

    question: str

    session_id: str

    created_at: datetime

    status: str = "NEW"