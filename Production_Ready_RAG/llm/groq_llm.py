import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class GroqLLM:

    def __init__(self):

        self.client = OpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url=os.getenv("GROQ_BASE_URL")
        )

        self.model = os.getenv(
            "GROQ_MODEL",
            "llama-3.3-70b-versatile"
        )

    def generate(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        top_p: float = 1.0
    ) -> str:

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response.choices[0].message.content