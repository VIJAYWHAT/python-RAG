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

        request_params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens
        }

        if reasoning_effort is not None:

            request_params["reasoning_effort"] = reasoning_effort

            # We do not need reasoning text in the application response
            request_params["include_reasoning"] = False

        response = self.client.chat.completions.create(
            **request_params
        )

        return LLMResponse(
            content=response.choices[0].message.content or "",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens
        )