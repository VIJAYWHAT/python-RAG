from pydantic import BaseModel


class ChatRequest(BaseModel):

    question: str

    session_id: str = "default-session"


class ChatResponseSchema(BaseModel):

    answer: str

    session_id: str

    guardrail_status: str | None = None

    guardrail_reason: str | None = None

    prompt_tokens: int | None = None

    completion_tokens: int | None = None

    total_tokens: int | None = None