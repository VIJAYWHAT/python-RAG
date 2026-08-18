from llm.base_llm import BaseLLM


class ContextChecker:

    def __init__(
        self,
        llm: BaseLLM
    ):
        self.llm = llm

    def is_answerable(
        self,
        question: str,
        documents: list
    ) -> bool:

        print("\n========================================")
        print("[CONTEXT CHECK DEBUG]")
        print("========================================")
        print(f"Question       : {question}")
        print(f"Documents      : {len(documents)}")

        # --------------------------------
        # No documents retrieved
        # --------------------------------

        if not documents:

            print("[CONTEXT CHECK] No documents retrieved")
            return False

        # --------------------------------
        # Check whether documents contain
        # actual text
        # --------------------------------

        valid_documents = []

        for document in documents:

            content = getattr(
                document,
                "content",
                ""
            )

            if content and content.strip():

                valid_documents.append(
                    content.strip()
                )

        print(
            f"[CONTEXT CHECK] "
            f"Valid documents: {len(valid_documents)}"
        )

        # --------------------------------
        # If documents contain content,
        # let the answer LLM work with them.
        # --------------------------------

        if not valid_documents:

            print(
                "[CONTEXT CHECK] "
                "Documents contain no usable content"
            )

            return False

        # --------------------------------
        # Combine retrieved content
        # --------------------------------

        context = "\n\n".join(
            valid_documents
        )

        # Limit context sent to classifier
        context = context[:12000]

        prompt = f"""
You are checking whether the provided HR knowledge
base context contains enough information to answer
the user's question.

User question:
{question}

Knowledge base context:
{context}

Rules:

1. If the context contains information that can directly
   or reasonably answer the question, return YES.

2. If the context is related to the question and contains
   relevant information, return YES.

3. Only return NO when the context is clearly unrelated
   or contains no useful information.

4. Do not require an exact sentence match.

5. Do not answer the question.

Return ONLY:

YES

or

NO
"""

        try:

            response = self.llm.generate(
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0,
                max_tokens=20
            )

            raw_result = (
                response.content or ""
            ).strip()

            result = raw_result.upper()

            print(
                f"[CONTEXT CHECK] "
                f"Raw Response={repr(raw_result)}"
            )

            print(
                f"[CONTEXT CHECK] "
                f"Parsed Result={repr(result)}"
            )

            if result == "YES":

                print(
                    "[CONTEXT CHECK] "
                    "Answerable = TRUE"
                )

                return True

            if result == "NO":

                print(
                    "[CONTEXT CHECK] "
                    "Answerable = FALSE"
                )

                return False

            # --------------------------------
            # Unexpected response
            # --------------------------------

            print(
                "[CONTEXT CHECK] "
                "Unexpected response. "
                "Falling back to retrieved documents."
            )

            # Since we already have valid retrieved
            # documents, allow the answer LLM to decide.
            return True

        except Exception as e:

            print(
                f"[CONTEXT CHECK ERROR] "
                f"{type(e).__name__}: {e}"
            )

            # --------------------------------
            # Fail open for RAG
            # --------------------------------

            # Retrieval already found usable documents,
            # so allow answer generation.
            return True