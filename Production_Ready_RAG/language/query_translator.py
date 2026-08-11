from llm.base_llm import BaseLLM


class QueryTranslator:

    def __init__(self, llm: BaseLLM):

        self.llm = llm

    def translate_to_english(
        self,
        question: str
    ) -> str:

        prompt = f"""
Translate the following user question into English.

Rules:

1. Preserve the exact meaning.
2. Do not answer the question.
3. Do not add information.
4. Return only the translated English question.
5. If the question is already in English, return it unchanged.

User question:

{question}
"""

        response = self.llm.generate(
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
            max_tokens=100
        )

        return response.content.strip()