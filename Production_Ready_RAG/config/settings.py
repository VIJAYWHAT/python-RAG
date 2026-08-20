"""
Central, environment-driven configuration.

Nothing in the codebase should read os.environ directly. Import
`settings` from here instead, so that every deployment knob is
visible in one place and documented in `.env.example`.
"""

from functools import lru_cache
from typing import Annotated, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


# ------------------------------------------------------------------
# List-valued settings
# ------------------------------------------------------------------
#
# For a complex field type, pydantic-settings JSON-decodes the raw
# environment string BEFORE any validator runs. That makes the
# natural way to write these:
#
#     ALLOWED_HOSTS=chat.ejadah.ae,localhost
#
# a hard startup failure, because it is not valid JSON - and the
# failure is a SettingsError at import time, before logging is even
# configured.
#
# `NoDecode` suppresses that decode step and hands the raw string to
# our own `_split_csv` validator, which accepts both a comma-
# separated list and a JSON array.
# ------------------------------------------------------------------

CsvList = Annotated[List[str], NoDecode]


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # ==============================================================
    # Runtime
    # ==============================================================

    environment: str = Field(
        default="production",
        description="local | staging | production"
    )

    debug: bool = Field(
        default=False,
        description="Verbose request/response logging. Never enable "
                    "in production: prompts contain employee data."
    )

    host: str = "0.0.0.0"

    port: int = 8000

    workers: int = Field(
        default=1,
        description="Keep at 1 unless the memory backend is shared. "
                    "The rate limiter and token cache are in-process."
    )

    log_level: str = "INFO"

    log_file: str = "logs/app.log"

    # ==============================================================
    # HTTP surface
    # ==============================================================

    # The Flutter mobile app is not a browser, so CORS does not
    # apply to it. These entries exist for the web build and local
    # tooling only. "*" is rejected by validate_for_production().
    cors_allow_origins: CsvList = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # Socket.IO keeps its own origin list. Mobile clients send no
    # Origin header, which python-socketio always allows, so this
    # list only gates browser clients.
    socket_cors_allow_origins: CsvList = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # TrustedHost protection. Set to the public hostname(s).
    allowed_hosts: CsvList = Field(
        default_factory=lambda: ["*"]
    )

    # ==============================================================
    # Ejadah backend (source of truth for identity + employee data)
    # ==============================================================

    ejadah_api_base_url: str = Field(
        default="https://ej-staging.usis.in:3583/fusiondev/api/",
        description="Must end with a trailing slash. Mirrors "
                    "api_base_url in the Flutter app's "
                    "lib/src/config/ejadhaconfig.dart"
    )

    ejadah_api_timeout_seconds: float = 20.0

    ejadah_api_max_retries: int = 2

    ejadah_verify_ssl: bool = Field(
        default=True,
        description="Only disable for a staging host with a broken "
                    "certificate chain, never in production."
    )

    ejadah_allow_legacy_tls_renegotiation: bool = Field(
        default=True,
        description="The Ejadah gateway requires unsafe legacy TLS "
                    "renegotiation; the Flutter app enables the same "
                    "flag in main.dart. OpenSSL 3 refuses it by "
                    "default, which would make every call fail."
    )

    ejadah_identity_route: str = Field(
        default="",
        description="Optional. The name of an Ejadah route that "
                    "resolves the caller from the bearer token ALONE "
                    "(no employee id in the body) and returns the "
                    "owning employee number. Setting this makes "
                    "identity verification exact instead of relying "
                    "on an echo check - see ejadah/identity_service.py. "
                    "Leave empty until such an endpoint exists."
    )

    ejadah_identity_response_keys: CsvList = Field(
        default_factory=lambda: [
            "EmployeeNumber",
            "EMPLOYEENUMBER",
            "EmployeeId",
            "EMPLOYEEID",
        ],
        description="Keys to look for in EJADAH_IDENTITY_ROUTE's "
                    "Response object when reading the employee number."
    )

    # How long a verified token -> employee binding is trusted
    # before the Ejadah API is asked again.
    identity_cache_ttl_seconds: int = 300

    # How long employee data (profile, leave, letters) is cached per
    # employee. Keep this short: HR data changes during the day.
    employee_cache_ttl_seconds: int = 60

    # ==============================================================
    # Employee data source
    # ==============================================================

    employee_data_source: str = Field(
        default="ejadah_api",
        description="ejadah_api (production) | local_db (offline dev "
                    "against data/hr_employee.db)"
    )

    # ==============================================================
    # LLM
    # ==============================================================

    groq_api_key: str = ""

    groq_base_url: str = "https://api.groq.com/openai/v1"

    groq_answer_model: str = "openai/gpt-oss-120b"

    groq_rewrite_model: str = "openai/gpt-oss-20b"

    llm_answer_temperature: float = 0.3

    llm_answer_max_tokens: int = 1024

    llm_timeout_seconds: float = 60.0

    # ==============================================================
    # RAG
    # ==============================================================

    vector_db_path: str = "data/vector_db"

    vector_db_collection: str = "hr_knowledge_base"

    embedding_model_name: str = "all-MiniLM-L6-v2"

    retrieval_top_k: int = 3

    knowledge_base_path: str = "data/company_info"

    # ==============================================================
    # Memory / persistence
    # ==============================================================

    chat_memory_db_path: str = "data/chat_memory.db"

    hr_query_db_path: str = "data/hr_queries.db"

    local_employee_db_path: str = "data/hr_employee.db"

    history_message_limit: int = 20

    # Conversation retention, enforced on startup and by the
    # /api/admin/purge-memory endpoint.
    memory_retention_days: int = 90

    # ==============================================================
    # Abuse protection
    # ==============================================================

    rate_limit_max_requests: int = 15

    rate_limit_window_seconds: int = 60

    max_question_length: int = 1000

    # Shared secret for the /api/admin/* maintenance endpoints.
    # Leave empty to disable those endpoints entirely.
    admin_api_key: str = ""

    # ==============================================================
    # Validators
    # ==============================================================

    @field_validator(
        "cors_allow_origins",
        "socket_cors_allow_origins",
        "allowed_hosts",
        "ejadah_identity_response_keys",
        mode="before"
    )
    @classmethod
    def _split_csv(cls, value):
        """
        Accepts either form, because both appear in the wild:

            ALLOWED_HOSTS=chat.ejadah.ae,localhost
            ALLOWED_HOSTS=["chat.ejadah.ae","localhost"]

        These fields are `CsvList`, so pydantic-settings hands us the
        raw string and does not decode JSON itself - which means this
        validator has to.
        """

        if not isinstance(value, str):
            return value

        value = value.strip()

        if not value:
            return []

        if value.startswith("["):

            import json

            try:
                decoded = json.loads(value)

            except ValueError as error:

                raise ValueError(
                    f"Value looks like a JSON array but does not "
                    f"parse: {error}"
                ) from error

            if not isinstance(decoded, list):

                raise ValueError(
                    "Expected a JSON array or a comma-separated list"
                )

            return [
                str(item).strip()
                for item in decoded
                if str(item).strip()
            ]

        return [
            item.strip()
            for item in value.split(",")
            if item.strip()
        ]

    @field_validator("ejadah_api_base_url")
    @classmethod
    def _require_trailing_slash(cls, value: str) -> str:

        value = value.strip()

        if not value:
            raise ValueError("EJADAH_API_BASE_URL must be set")

        return value if value.endswith("/") else value + "/"

    @field_validator("employee_data_source")
    @classmethod
    def _known_source(cls, value: str) -> str:

        allowed = {"ejadah_api", "local_db"}

        value = value.strip().lower()

        if value not in allowed:

            raise ValueError(
                f"EMPLOYEE_DATA_SOURCE must be one of {sorted(allowed)}"
            )

        return value

    # ==============================================================
    # Derived helpers
    # ==============================================================

    @property
    def is_production(self) -> bool:

        return self.environment.strip().lower() == "production"

    def ejadah_url(self, route: str) -> str:

        return self.ejadah_api_base_url + route.lstrip("/")

    def validate_for_production(self) -> List[str]:
        """
        Returns the list of misconfigurations that must be fixed
        before going live. Called once at startup.
        """

        problems: List[str] = []

        if not self.groq_api_key:
            problems.append("GROQ_API_KEY is not set")

        if not self.is_production:
            return problems

        if self.debug:
            problems.append(
                "DEBUG must be false in production (prompts contain "
                "employee data)"
            )

        if "*" in self.cors_allow_origins:
            problems.append(
                "CORS_ALLOW_ORIGINS must not contain '*' in production"
            )

        if "*" in self.socket_cors_allow_origins:
            problems.append(
                "SOCKET_CORS_ALLOW_ORIGINS must not contain '*' in "
                "production"
            )

        if "*" in self.allowed_hosts:
            problems.append(
                "ALLOWED_HOSTS must name the real public hostname(s) "
                "in production"
            )

        if not self.ejadah_verify_ssl:
            problems.append(
                "EJADAH_VERIFY_SSL must be true in production"
            )

        if self.employee_data_source != "ejadah_api":
            problems.append(
                "EMPLOYEE_DATA_SOURCE must be 'ejadah_api' in "
                "production; 'local_db' serves demo data"
            )

        return problems


@lru_cache
def get_settings() -> Settings:

    return Settings()


settings = get_settings()
