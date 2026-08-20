from openai import OpenAI

from config.settings import settings
from core.logging_config import get_logger
from llm.base_llm import BaseLLM
from models.llm_response import LLMResponse


logger = get_logger(__name__)


class GroqLLM(BaseLLM):
    """
    Groq-hosted OpenAI-compatible chat model.

    Note for reviewers: prompts sent from here contain the
    employee's own HR data. That is inherent to the product, but it
    means the model provider is a data processor - keep
    GROQ_API_KEY out of source control, and prefer a zero-retention
    agreement with the provider.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None
    ):

        key = api_key or settings.groq_api_key

        if not key:
            raise RuntimeError(
                "GROQ_API_KEY is not configured; the assistant "
                "cannot generate answers."
            )

        self.client = OpenAI(
            api_key=key,
            base_url=base_url or settings.groq_base_url,
            timeout=timeout or settings.llm_timeout_seconds,
            max_retries=2
        )

        self.model = model or settings.groq_answer_model

        self.default_temperature = settings.llm_answer_temperature

        self.default_max_tokens = settings.llm_answer_max_tokens

    def generate(
        self,
        messages,
        temperature=None,
        max_tokens=None,
        reasoning_effort=None
    ):

        if temperature is None:
            temperature = self.default_temperature

        if max_tokens is None:
            max_tokens = self.default_max_tokens

        base_params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens
        }

        request_params = dict(base_params)

        if reasoning_effort is not None:

            request_params["reasoning_effort"] = reasoning_effort

            # We never need the reasoning text in the app response
            request_params["include_reasoning"] = False

        try:

            response = self.client.chat.completions.create(
                **request_params
            )

        except Exception as error:

            # Some providers/models reject the reasoning params.
            # Retry once without them instead of failing the call.
            if reasoning_effort is None:
                raise

            logger.warning(
                "Reasoning params rejected by %s (%s: %s); "
                "retrying without them",
                self.model,
                type(error).__name__,
                error
            )

            response = self.client.chat.completions.create(
                **base_params
            )

        message = response.choices[0].message

        content = (message.content or "").strip()

        # Reasoning models occasionally return the answer in the
        # reasoning channel with an empty content field.
        if not content:

            fallback = (
                getattr(message, "reasoning", None)
                or getattr(message, "reasoning_content", None)
                or ""
            )

            content = str(fallback).strip()

            if content:

                logger.info(
                    "%s returned empty content; used the reasoning "
                    "channel instead",
                    self.model
                )

        usage = getattr(response, "usage", None)

        return LLMResponse(
            content=content,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0
        )
