from dataclasses import dataclass
from typing import List, Optional

from models.document import Document
from models.llm_response import LLMResponse


@dataclass
class ChatResponse:

    answer: str

    source_documents: List[Document]

    llm_response: Optional[LLMResponse] = None

    guardrail_status: Optional[str] = None

    guardrail_reason: Optional[str] = None