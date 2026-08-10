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
            "llama-3.3-70b-versatile"
        )

    def generate(
        self,
        messages: list,
        temperature: float = 0.2,
        max_tokens: int = 1024
    ) -> LLMResponse:

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

        return LLMResponse(
            content=response.choices[0].message.content,
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            total_tokens=response.usage.total_tokens
        )