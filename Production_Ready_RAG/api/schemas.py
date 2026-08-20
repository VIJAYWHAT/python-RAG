"""
Request and response models.

Note what is NOT in the request models: there is no `employee_id`
field on ChatRequest. The employee is derived from the token, so
there is no field a client could set to ask about somebody else.
The optional `X-Employee-Id` header exists only as a cross-check
(see ejadah/identity_service.py) and never as an input to data
access.
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from config.settings import settings


# ==================================================================
# Chat
# ==================================================================


class ChatRequest(BaseModel):

    model_config = ConfigDict(extra="forbid")

    question: str = Field(
        ...,
        min_length=1,
        max_length=settings.max_question_length,
        description="The employee's HR question"
    )

    session_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Conversation thread id. Omit to start a new "
                    "thread; the response carries the id to reuse."
    )

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:

        cleaned = value.strip()

        if not cleaned:
            raise ValueError("The question cannot be empty")

        return cleaned


class ChatResponseSchema(BaseModel):

    answer: str

    session_id: str

    employee_id: str

    guardrail_status: Optional[str] = None

    guardrail_reason: Optional[str] = None

    prompt_tokens: Optional[int] = None

    completion_tokens: Optional[int] = None

    total_tokens: Optional[int] = None


# ==================================================================
# Identity
# ==================================================================


class MeResponse(BaseModel):

    employee_id: str

    name: Optional[str] = None

    designation: Optional[str] = None

    department: Optional[str] = None

    # Which verification layers established this identity. Useful
    # when diagnosing a login problem; carries no secrets.
    verified_by: List[str] = Field(default_factory=list)


# ==================================================================
# History
# ==================================================================


class TranscriptMessage(BaseModel):

    role: str

    content: str

    language: Optional[str] = None

    created_at: Optional[str] = None


class TranscriptResponse(BaseModel):

    session_id: str

    employee_id: str

    messages: List[TranscriptMessage] = Field(default_factory=list)


class SessionSummary(BaseModel):

    session_id: str

    message_count: int

    started_at: Optional[str] = None

    last_message_at: Optional[str] = None


class SessionListResponse(BaseModel):

    employee_id: str

    sessions: List[SessionSummary] = Field(default_factory=list)


class NewSessionResponse(BaseModel):

    session_id: str

    employee_id: str


class SimpleStatusResponse(BaseModel):

    status: str = "ok"

    detail: Optional[str] = None


# ==================================================================
# Health
# ==================================================================


class HealthResponse(BaseModel):

    status: str

    service: str = "Ejadah HR AI Assistant"

    environment: str

    version: str


class ReadinessResponse(BaseModel):

    status: str

    checks: dict
