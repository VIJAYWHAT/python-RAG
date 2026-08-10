from llm.base_llm import BaseLLM

class QueryRewriter:

    def __init__(
        self,
        llm: BaseLLM
    ):
        self.llm = llm

    def rewrite(
        self,
        question: str,
        history: list
    ) -> str:

        messages = [
            {
                "role": "system",
                "content": """
You are a query rewriting assistant.

Rewrite the user's latest question so that it becomes a standalone question.

Use the previous conversation only to resolve references such as:
- it
- they
- this
- that
- he
- she

Do NOT answer the question.

Only return the rewritten standalone question.
"""
            }
        ]

        messages.extend(history)

        messages.append(
            {
                "role": "user",
                "content": question
            }
        )

        response = self.llm.generate(messages)

        return response.content.strip()