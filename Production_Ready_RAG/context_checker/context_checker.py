from llm.base_llm import BaseLLM

class ContextChecker:

    def __init__(self, llm: BaseLLM):
        self.llm = llm

    def is_answerable(
        self,
        question: str,
        documents
    ) -> bool:

        if not documents:
            return False

        context = "\n\n".join(
            document.content
            for document in documents
        )

        prompt = f"""
You are a knowledge base answerability checker.

Your task is to determine whether the provided knowledge
base context contains enough information to answer the
user's question.

User Question:
{question}

Knowledge Base Context:
{context}

Rules:

1. Return YES only when the context contains enough
   information to directly answer the question.

2. Return NO when the context is unrelated, incomplete,
   or does not contain enough information.

3. Do not use your own knowledge.

4. Do not guess or infer information that is not present
   in the context.

Return only one word:

YES

or

NO
"""

        response = self.llm.generate(
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
            max_tokens=5
        )

        result = response.content.strip().upper()

        return result == "YES"