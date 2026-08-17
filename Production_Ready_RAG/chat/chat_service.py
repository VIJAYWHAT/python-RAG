from llm.base_llm import BaseLLM
from models.chat_response import ChatResponse

from guardrails.guardrail_result import GuardrailStatus
from guardrails.guardrail_logger import GuardrailLogger

from context_checker.context_checker import ContextChecker
from hr_queries.hr_query_store import HRQueryStore

from language.language_detector import LanguageDetector
from language.query_translator import QueryTranslator

from employee.employee_query_detector import EmployeeQueryDetector
from employee.employee_context_builder import EmployeeContextBuilder


class ChatService:

    def __init__(
        self,
        retriever,
        prompt_builder,
        llm: BaseLLM,
        memory_manager,
        query_rewriter,
        guardrails,
        guardrail_logger: GuardrailLogger,
        context_checker: ContextChecker,
        hr_query_store: HRQueryStore,
        language_detector: LanguageDetector,
        query_translator: QueryTranslator
    ):

        self.llm = llm
        self.retriever = retriever
        self.prompt_builder = prompt_builder

        self.employee_context_builder = EmployeeContextBuilder()

        # Persistent conversation memory
        self.memory_manager = memory_manager

        self.query_rewriter = query_rewriter

        self.guardrails = guardrails
        self.guardrail_logger = guardrail_logger

        self.context_checker = context_checker
        self.hr_query_store = hr_query_store

        self.language_detector = language_detector
        self.query_translator = query_translator

    # ================================================================
    # Main entry point
    # ================================================================

    def ask(
        self,
        question: str,
        user_id: str,
        session_id: str = "default-session"
    ):

        # ------------------------------------------------------------
        # 1. Detect user language
        # ------------------------------------------------------------

        language = self.language_detector.detect_language(question)

        # ------------------------------------------------------------
        # 2. Session-specific memory
        # ------------------------------------------------------------

        history = self.memory_manager.get_messages(
            user_id=user_id,
            session_id=session_id
        )

        # ------------------------------------------------------------
        # 3. Prompt injection guardrail
        #    (runs BEFORE any database access)
        # ------------------------------------------------------------

        injection_result = self.guardrails.check_injection(question)

        if injection_result.status != GuardrailStatus.ALLOW:

            self.guardrail_logger.log_blocked(
                question=question,
                reason=injection_result.reason
            )

            return ChatResponse(
                answer=injection_result.message,
                source_documents=[],
                llm_response=None,
                guardrail_status="blocked",
                guardrail_reason=injection_result.reason
            )

        # ------------------------------------------------------------
        # 4. General conversation / greeting
        # ------------------------------------------------------------

        general_result = self.guardrails.check_general_conversation(
            question
        )

        if general_result.message:

            print(
                f"[GENERAL CHAT] "
                f"Question={question} | "
                f"Reason={general_result.reason}"
            )

            self._remember(
                user_id,
                session_id,
                question,
                general_result.message,
                language
            )

            return ChatResponse(
                answer=general_result.message,
                source_documents=[],
                llm_response=None,
                guardrail_status="greeting",
                guardrail_reason=general_result.reason
            )

        # ------------------------------------------------------------
        # 5. Query rewriting (resolves follow-up questions)
        # ------------------------------------------------------------

        if history:

            search_question = self.query_rewriter.rewrite(
                question,
                history
            )

        else:

            search_question = question

        print("\n========================================")
        print("[CHAT DEBUG]")
        print("========================================")
        print(f"Original Question     : {question}")
        print(f"Session ID            : {session_id}")
        print(f"User ID               : {user_id}")
        print(f"Detected Language     : {language}")
        print(f"History Count         : {len(history)}")
        print(f"Rewritten Question    : {search_question}")
        print("========================================\n")

        # ------------------------------------------------------------
        # 6. INTENT ROUTING
        #    Is this about the logged-in employee's own record?
        #
        #    Detection runs on BOTH the original question and the
        #    rewritten question, so follow-ups such as
        #    "what about next month?" are routed correctly.
        # ------------------------------------------------------------

        classification = EmployeeQueryDetector.classify(
            question,
            search_question
        )

        print("========================================")
        print("[INTENT ROUTER]")
        print("========================================")
        print(f"Question          : {question}")
        print(f"Rewritten         : {search_question}")
        print(f"Employee Query    : {classification['is_employee_query']}")
        print(f"Query Types       : {classification['query_types']}")
        print(f"Reason            : {classification['reason']}")
        print(
            "Route             : "
            + (
                "EMPLOYEE_DATA"
                if classification["is_employee_query"]
                else "HR_KNOWLEDGE (RAG)"
            )
        )
        print("========================================\n")

        if classification["is_employee_query"]:

            employee_response = self._answer_employee_question(
                question=question,
                search_question=search_question,
                user_id=user_id,
                session_id=session_id,
                language=language,
                history=history,
                query_types=classification["query_types"]
            )

            if employee_response is not None:
                return employee_response

            # If the employee record could not be resolved we
            # deliberately fall through to the RAG pipeline
            # instead of hard-failing.

        # ------------------------------------------------------------
        # 7. Scope guardrail (RAG path only)
        # ------------------------------------------------------------

        scope_result = self.guardrails.check_scope(search_question)

        if scope_result.status == GuardrailStatus.GREETING:

            greeting_message = (
                "Hi! How can I help you with your "
                "HR-related questions?"
            )

            self._remember(
                user_id,
                session_id,
                question,
                greeting_message,
                language
            )

            return ChatResponse(
                answer=greeting_message,
                source_documents=[],
                llm_response=None,
                guardrail_status="greeting",
                guardrail_reason=(
                    "General greeting or chatbot assistance request"
                )
            )

        if scope_result.status == GuardrailStatus.OUT_OF_SCOPE:

            self.guardrail_logger.log_out_of_scope(
                question=question,
                reason=scope_result.reason
            )

            return ChatResponse(
                answer=scope_result.message,
                source_documents=[],
                llm_response=None,
                guardrail_status="out_of_scope",
                guardrail_reason=scope_result.reason
            )

        # ------------------------------------------------------------
        # 8. Translate query for retrieval
        # ------------------------------------------------------------

        retrieval_question = self.query_translator.translate_to_english(
            search_question
        )

        print("\n========================================")
        print("[RETRIEVAL DEBUG]")
        print("========================================")
        print(f"Original Question  : {question}")
        print(f"Search Question    : {search_question}")
        print(f"Retrieval Question : {retrieval_question}")
        print("========================================\n")

        # ------------------------------------------------------------
        # 9. Retrieve documents
        # ------------------------------------------------------------

        documents = self.retriever.retrieve(retrieval_question)

        self._print_documents(question, documents)

        # ------------------------------------------------------------
        # 10. Context check
        # ------------------------------------------------------------

        answerable = self.context_checker.is_answerable(
            question=retrieval_question,
            documents=documents
        )

        print(
            f"[CONTEXT RESULT] "
            f"Question={question} | "
            f"Answerable={answerable}"
        )

        if not answerable:

            self.hr_query_store.save_query(
                question=question,
                session_id=session_id
            )

            return ChatResponse(
                answer=(
                    "I couldn't find this information in the "
                    "available HR knowledge base. Your query "
                    "has been recorded for HR review."
                ),
                source_documents=documents,
                llm_response=None,
                guardrail_status="allow",
                guardrail_reason=(
                    "No sufficient information found "
                    "in knowledge base"
                )
            )

        # ------------------------------------------------------------
        # 11. Build prompt (original question keeps the language)
        #
        #     If the question referred to the user in the first
        #     person but we could not pin down a specific topic
        #     ("how much do I get paid?", "can I apply for this?"),
        #     attach the employee record as well. The scope
        #     guardrail has already run, so this is safe.
        # ------------------------------------------------------------

        soft_employee_context = None

        if classification["query_types"]:

            candidate = self.employee_context_builder.build(
                employee_id=user_id,
                query_types=classification["query_types"]
            )

            if candidate and candidate.get("found"):

                soft_employee_context = candidate

                print(
                    f"[INTENT ROUTER] "
                    f"Attaching employee record as supporting "
                    f"context (soft match: "
                    f"{classification['query_types']})"
                )

        if soft_employee_context:

            messages = self.prompt_builder.build_employee_messages(
                question=question,
                employee_context=soft_employee_context["text"],
                documents=documents,
                history=history,
                language=language
            )

        else:

            messages = self.prompt_builder.build_messages(
                question,
                documents,
                history,
                language
            )

        # ------------------------------------------------------------
        # 12. Generate answer
        # ------------------------------------------------------------

        llm_response = self.llm.generate(messages)

        answer = (llm_response.content or "").strip()

        if not answer:

            answer = (
                "I'm sorry, I couldn't generate an answer just "
                "now. Please try asking again."
            )

        # ------------------------------------------------------------
        # 13. Save conversation
        # ------------------------------------------------------------

        self._remember(
            user_id,
            session_id,
            question,
            answer,
            language
        )

        return ChatResponse(
            answer=answer,
            source_documents=documents,
            llm_response=llm_response,
            guardrail_status="allow",
            guardrail_reason="Request passed guardrails"
        )

    # ================================================================
    # Employee-specific answering path
    # ================================================================

    def _answer_employee_question(
        self,
        question,
        search_question,
        user_id,
        session_id,
        language,
        history,
        query_types
    ):
        """
        Returns a ChatResponse, or None if the employee record
        could not be resolved (caller then falls back to RAG).
        """

        print("========================================")
        print("[EMPLOYEE QUERY]")
        print("========================================")
        print(f"Employee ID : {user_id}")
        print(f"Question    : {question}")
        print(f"Query Types : {query_types}")

        employee_context = self.employee_context_builder.build(
            employee_id=user_id,
            query_types=query_types
        )

        if not employee_context or not employee_context.get("found"):

            print(
                f"[EMPLOYEE QUERY] "
                f"No employee record found for '{user_id}'. "
                f"Falling back to the HR knowledge base."
            )

            return None

        print("[EMPLOYEE QUERY] Record found. Context sent to LLM:")
        print("----------------------------------------")
        print(employee_context["text"])
        print("----------------------------------------")

        # ------------------------------------------------------------
        # Also pull policy documents so hybrid questions work, e.g.
        # "how many casual leaves are left and what is the policy?"
        # ------------------------------------------------------------

        documents = []

        try:

            retrieval_question = (
                self.query_translator.translate_to_english(
                    search_question
                )
            )

            documents = self.retriever.retrieve(retrieval_question)

            print(
                f"[EMPLOYEE QUERY] "
                f"Supporting policy documents: {len(documents)}"
            )

        except Exception as error:

            print(
                f"[EMPLOYEE QUERY] "
                f"Policy retrieval skipped: "
                f"{type(error).__name__}: {error}"
            )

            documents = []

        # ------------------------------------------------------------
        # Build the employee prompt and answer
        # ------------------------------------------------------------

        messages = self.prompt_builder.build_employee_messages(
            question=question,
            employee_context=employee_context["text"],
            documents=documents,
            history=history,
            language=language
        )

        llm_response = self.llm.generate(messages)

        answer = (llm_response.content or "").strip()

        if not answer:

            answer = (
                "I'm sorry, I couldn't generate an answer just "
                "now. Please try asking again."
            )

        print("[EMPLOYEE QUERY] Answer generated from database data.")

        self._remember(
            user_id,
            session_id,
            question,
            answer,
            language
        )

        return ChatResponse(
            answer=answer,
            source_documents=documents,
            llm_response=llm_response,
            guardrail_status="allow",
            guardrail_reason=(
                "Answered from the authenticated employee's "
                "own HR record"
            )
        )

    # ================================================================
    # Helpers
    # ================================================================

    def _remember(
        self,
        user_id,
        session_id,
        question,
        answer,
        language
    ):

        self.memory_manager.add_user_message(
            user_id=user_id,
            session_id=session_id,
            content=question,
            language=language
        )

        self.memory_manager.add_assistant_message(
            user_id=user_id,
            session_id=session_id,
            content=answer,
            language=language
        )

    @staticmethod
    def _print_documents(question, documents):

        print("\n========================================")
        print("[RAG DEBUG]")
        print("========================================")
        print(f"Question          : {question}")
        print(f"Retrieved Docs    : {len(documents)}")

        for index, document in enumerate(documents):
            print(f"Document {index + 1}: {document}")

        print("========================================\n")
