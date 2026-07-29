from typing import List
from models.document import Document


class PromptBuilder:

    def build_prompt(
        self,
        query: str,
        documents: List[Document]
    ) -> str:

        context = "\n\n".join(
            document.content
            for document in documents
        )

        prompt = f"""
You are a HR AI to Usis Technologies.

Answer ONLY using the provided context.

If the answer cannot be found in the context, say:

"I couldn't find that information in the provided documents."

Context:
{context}

Question:
{query}

Answer:
"""

        return prompt.strip()