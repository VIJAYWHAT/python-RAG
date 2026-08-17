import os

from dotenv import load_dotenv
from openai import OpenAI
from llm.base_llm import BaseLLM
from models.llm_response import LLMResponse

load_dotenv()


class GroqLLM(BaseLLM):

    def __init__(
        self,
        model: str | None = None
    ):

        self.client = OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url=os.getenv("GROQ_BASE_URL")
        )

        self.model = model or os.getenv(
            "GROQ_MODEL",
            "openai/gpt-oss-120b"
        )

    def generate(
        self,
        messages,
        temperature=0.7,
        max_tokens=1024,
        reasoning_effort=None
    ):

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

            print(
                f"[GROQ LLM] Reasoning params rejected "
                f"({type(error).__name__}: {error}). "
                f"Retrying without them."
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

                print(
                    "[GROQ LLM] content was empty; "
                    "used the reasoning channel instead."
                )

        return LLMResponse(
            content=content,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens
        )
