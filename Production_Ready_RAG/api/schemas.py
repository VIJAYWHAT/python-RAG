from pydantic import BaseModel, Field


class ChatRequest(BaseModel):

    question: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="HR-related question"
    )

    session_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Chat session identifier"
    )


class ChatResponseSchema(BaseModel):

    answer: str

    session_id: str

    guardrail_status: str | None = None

    guardrail_reason: str | None = None

    prompt_tokens: int | None = None

    completion_tokens: int | None = None

    total_tokens: int | None = None