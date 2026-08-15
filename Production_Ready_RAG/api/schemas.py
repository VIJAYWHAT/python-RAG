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


# ==================================================================
# Authentication
# ==================================================================


class LoginRequest(BaseModel):

    employee_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Employee ID, for example employee-001",
        examples=["employee-001"]
    )

    password: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Employee password",
        examples=["Test@123"]
    )


class LoginResponse(BaseModel):

    token: str = Field(
        ...,
        description="Session token to use as the Bearer token "
                    "and in the Socket.IO auth handshake"
    )

    employee_id: str

    name: str | None = None

    designation: str | None = None

    department: str | None = None


class MeResponse(BaseModel):

    employee_id: str

    name: str | None = None

    designation: str | None = None

    department: str | None = None

    manager_name: str | None = None

    location: str | None = None
