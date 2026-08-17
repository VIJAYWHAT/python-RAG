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
        # Check whether documents contain actual text
        # --------------------------------

        valid_documents = []

        for document in documents:

            content = getattr(document, "content", "")

            if content and content.strip():
                valid_documents.append(content.strip())

        print(
            f"[CONTEXT CHECK] "
            f"Valid documents: {len(valid_documents)}"
        )

        if not valid_documents:

            print(
                "[CONTEXT CHECK] "
                "Documents contain no usable content"
            )

            return False

        context = "\n\n".join(valid_documents)[:12000]

        prompt = f"""
You are checking whether the provided HR knowledge base context
contains enough information to answer the user's question.

User question:
{question}

Knowledge base context:
{context}

Rules:

1. If the context contains information that can directly or
   reasonably answer the question, return YES.
2. If the context is related to the question and contains
   relevant information, return YES.
3. Only return NO when the context is clearly unrelated or
   contains no useful information.
4. Do not require an exact sentence match.
5. Do not answer the question.

Return ONLY the single word YES or NO.
"""

        try:

            # NOTE:
            # openai/gpt-oss-* are reasoning models. With a very
            # small token budget the whole budget is spent on
            # reasoning and message.content comes back EMPTY.
            # That is why this used to log Raw Response=''.
            #
            # Fix: low reasoning effort + a real token budget.

            response = self._generate(prompt)

            raw_result = (response.content or "").strip()

            result = raw_result.upper()

            print(
                f"[CONTEXT CHECK] "
                f"Raw Response={repr(raw_result)}"
            )

            # --------------------------------
            # Tolerant parsing
            # --------------------------------

            decision = self._parse(result)

            print(f"[CONTEXT CHECK] Parsed Result={repr(decision)}")

            if decision is True:
                print("[CONTEXT CHECK] Answerable = TRUE")
                return True

            if decision is False:
                print("[CONTEXT CHECK] Answerable = FALSE")
                return False

            print(
                "[CONTEXT CHECK] "
                "Unexpected response. "
                "Falling back to retrieved documents."
            )

            # We already have usable documents, so let the
            # answer LLM decide.
            return True

        except Exception as e:

            print(
                f"[CONTEXT CHECK ERROR] "
                f"{type(e).__name__}: {e}"
            )

            # Fail open for RAG
            return True

    # ================================================================
    # Helpers
    # ================================================================

    def _generate(self, prompt):

        messages = [
            {
                "role": "user",
                "content": prompt
            }
        ]

        try:

            return self.llm.generate(
                messages=messages,
                temperature=0,
                max_tokens=512,
                reasoning_effort="low"
            )

        except TypeError:

            # LLM implementation without reasoning_effort support
            return self.llm.generate(
                messages=messages,
                temperature=0,
                max_tokens=512
            )

    @staticmethod
    def _parse(result):
        """
        Returns True / False / None (unknown).
        """

        if not result:
            return None

        if result in ("YES", "NO"):
            return result == "YES"

        # The model sometimes wraps the verdict in a sentence.
        has_yes = "YES" in result
        has_no = "NO" in result

        if has_yes and not has_no:
            return True

        if has_no and not has_yes:
            return False

        # Ambiguous: prefer the last occurrence
        if has_yes and has_no:
            return result.rfind("YES") > result.rfind("NO")

        return None
