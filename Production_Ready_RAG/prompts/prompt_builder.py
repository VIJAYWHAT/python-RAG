class PromptBuilder:

    def build_messages(
        self,
        question: str,
        documents: list,
        history: list,
        language="English"
    ) -> list:

        context = "\n\n".join(
            document.content
            for document in documents
        )

        system_prompt = f"""
You are an HR representative AI Assistant of Usis Technologies.

Answer the user's question using ONLY the provided context.

If the answer cannot be found in the context,
reply:

"I don't have enough information to answer that."

Context:

{context}
"""

        messages = [
            {
                "role": "system",
                "content": system_prompt.strip()
            }
        ]

        messages.extend(history)

        messages.append(
            {
                "role": "user",
                "content": question
            }
        )

        return messages