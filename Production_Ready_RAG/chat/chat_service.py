"""
The chat pipeline.

`ask()` takes a VERIFIED `Principal` rather than an employee id
string. That is the whole security design in one signature: there
is no way to call this service without having already proved who
the caller is, and no parameter through which a different employee
could be named.

Order of the pipeline, and why:

  1. Injection guard      - runs before any HR data is fetched, so a
                            hijack attempt never reaches the gateway
  2. Small talk           - answered locally, no LLM, no data
  3. Query rewrite        - resolves "what about next month?"
  4. Intent routing       - own record (HR APIs) or policy (RAG)?
  5. Scope guard          - RAG path only
  6. Retrieve + verify    - is the answer actually in the documents?
  7. Generate
  8. Output guard         - last check before the answer is returned
  9. Remember             - stored under the employee-scoped key
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.errors import (
    AppError,
    AuthenticationError,
    UpstreamUnavailableError,
)
from core.logging_config import get_logger, log_personal, mask_employee
from context_checker.context_checker import ContextChecker
from employee.employee_query_detector import EmployeeQueryDetector
from ejadah.identity_service import Principal
from guardrails.guardrail_logger import GuardrailLogger
from guardrails.guardrail_result import GuardrailStatus
from guardrails.output_guard import OutputGuard
from hr_queries.hr_query_store import HRQueryStore
from language.language_detector import LanguageDetector
from language.query_translator import QueryTranslator
from llm.base_llm import BaseLLM
from models.chat_response import ChatResponse
from session.session_manager import SessionManager


logger = get_logger(__name__)


UPSTREAM_DOWN_MESSAGE = (
    "I can't reach the HR system for your details right now. "
    "Please try again in a moment - the HR policy questions still "
    "work in the meantime."
)

GENERIC_FAILURE_MESSAGE = (
    "Something went wrong while preparing your answer. "
    "Please try again."
)


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
        query_translator: QueryTranslator,
        employee_context_provider,
        output_guard: Optional[OutputGuard] = None,
        retrieval_top_k: int = 3
    ):

        self.retriever = retriever
        self.prompt_builder = prompt_builder
        self.llm = llm

        self.memory_manager = memory_manager
        self.query_rewriter = query_rewriter

        self.guardrails = guardrails
        self.guardrail_logger = guardrail_logger
        self.output_guard = output_guard or OutputGuard()

        self.context_checker = context_checker
        self.hr_query_store = hr_query_store

        self.language_detector = language_detector
        self.query_translator = query_translator

        self.employee_context_provider = employee_context_provider

        self.retrieval_top_k = retrieval_top_k

    # ==============================================================
    # Main entry point
    # ==============================================================

    def ask(
        self,
        question: str,
        principal: Principal,
        session_id: str = "default-session"
    ) -> ChatResponse:

        employee_id = principal.employee_id

        session_id = SessionManager.validate(session_id)

        memory_key = SessionManager.scope(employee_id, session_id)

        logger.info(
            "Chat request | employee=%s session=%s length=%s",
            mask_employee(employee_id),
            session_id,
            len(question or "")
        )

        log_personal(logger, "Question: %s", question)

        language = self.language_detector.detect_language(question)

        history = self.memory_manager.get_messages(
            user_id=employee_id,
            session_id=memory_key
        )

        # ----------------------------------------------------------
        # 1. Prompt injection - before any HR data is touched
        # ----------------------------------------------------------

        injection = self.guardrails.check_injection(question)

        if injection.status != GuardrailStatus.ALLOW:

            self.guardrail_logger.log_blocked(
                question=question,
                reason=injection.reason
            )

            logger.warning(
                "Blocked a request from employee=%s | reason=%s",
                mask_employee(employee_id),
                injection.reason
            )

            return ChatResponse(
                answer=injection.message,
                source_documents=[],
                llm_response=None,
                guardrail_status="blocked",
                guardrail_reason=injection.reason
            )

        # ----------------------------------------------------------
        # 2. Greetings and "what can you do" - no LLM, no data
        # ----------------------------------------------------------

        small_talk = self.guardrails.check_general_conversation(question)

        if small_talk.message:

            self._remember(
                employee_id,
                memory_key,
                question,
                small_talk.message,
                language
            )

            return ChatResponse(
                answer=small_talk.message,
                source_documents=[],
                llm_response=None,
                guardrail_status="greeting",
                guardrail_reason=small_talk.reason
            )

        # ----------------------------------------------------------
        # 3. Rewrite follow-ups into standalone questions
        # ----------------------------------------------------------

        search_question = question

        if history:

            try:
                search_question = self.query_rewriter.rewrite(
                    question,
                    history
                ) or question

            except Exception as error:

                logger.warning(
                    "Query rewrite failed (%s); using the original "
                    "question",
                    type(error).__name__
                )

        # ----------------------------------------------------------
        # 4. Intent routing
        # ----------------------------------------------------------

        classification = EmployeeQueryDetector.classify(
            question,
            search_question
        )

        logger.info(
            "Routing | employee=%s route=%s topics=%s reason=%s",
            mask_employee(employee_id),
            "EMPLOYEE_DATA"
            if classification["is_employee_query"]
            else "HR_KNOWLEDGE",
            classification["query_types"],
            classification["reason"]
        )

        if classification["is_employee_query"]:

            response = self._answer_from_employee_record(
                question=question,
                search_question=search_question,
                principal=principal,
                memory_key=memory_key,
                session_id=session_id,
                language=language,
                history=history,
                query_types=classification["query_types"]
            )

            if response is not None:
                return response

            # The record could not be resolved; fall through to the
            # knowledge base rather than hard-failing.

        # ----------------------------------------------------------
        # 5. Scope guard (RAG path only)
        # ----------------------------------------------------------

        scope = self.guardrails.check_scope(search_question)

        if scope.status == GuardrailStatus.GREETING:

            greeting = (
                "Hi! How can I help you with your HR-related "
                "questions?"
            )

            self._remember(
                employee_id, memory_key, question, greeting, language
            )

            return ChatResponse(
                answer=greeting,
                source_documents=[],
                llm_response=None,
                guardrail_status="greeting",
                guardrail_reason="General greeting"
            )

        if scope.status == GuardrailStatus.OUT_OF_SCOPE:

            self.guardrail_logger.log_out_of_scope(
                question=question,
                reason=scope.reason
            )

            return ChatResponse(
                answer=scope.message,
                source_documents=[],
                llm_response=None,
                guardrail_status="out_of_scope",
                guardrail_reason=scope.reason
            )

        # ----------------------------------------------------------
        # 6. Retrieve
        # ----------------------------------------------------------

        retrieval_question = self._translate(search_question)

        documents = self._retrieve(retrieval_question)

        answerable = self.context_checker.is_answerable(
            question=retrieval_question,
            documents=documents
        )

        if not answerable:

            # Worth knowing what employees are asking that the
            # knowledge base cannot answer.
            try:
                self.hr_query_store.save_query(
                    question=question,
                    session_id=session_id
                )

            except Exception as error:

                logger.warning(
                    "Could not record an unanswered query: %s: %s",
                    type(error).__name__,
                    error
                )

            return ChatResponse(
                answer=(
                    "I couldn't find this in the HR knowledge base. "
                    "Your question has been recorded for the HR team "
                    "to review."
                ),
                source_documents=documents,
                llm_response=None,
                guardrail_status="allow",
                guardrail_reason="Not covered by the knowledge base"
            )

        # ----------------------------------------------------------
        # 7. Build the prompt
        #
        # A first-person question with no clear topic ("can I apply
        # for this?") gets the employee's own record attached as
        # supporting context, because the answer usually depends on
        # it. The scope guard has already run, so this is safe.
        # ----------------------------------------------------------

        soft_context = None

        if classification["query_types"]:

            soft_context = self._try_build_employee_context(
                principal,
                classification["query_types"]
            )

        if soft_context and soft_context.get("found"):

            messages = self.prompt_builder.build_employee_messages(
                question=question,
                employee_context=soft_context["text"],
                documents=documents,
                history=history,
                language=language,
                employee_name=principal.employee_name
            )

        else:

            messages = self.prompt_builder.build_messages(
                question,
                documents,
                history,
                language
            )

        # ----------------------------------------------------------
        # 8. Generate + guard
        # ----------------------------------------------------------

        return self._generate_and_guard(
            messages=messages,
            question=question,
            principal=principal,
            memory_key=memory_key,
            language=language,
            documents=documents,
            guardrail_reason="Answered from the HR knowledge base"
        )

    # ==============================================================
    # Employee-record path
    # ==============================================================

    def _answer_from_employee_record(
        self,
        question: str,
        search_question: str,
        principal: Principal,
        memory_key: str,
        session_id: str,
        language: str,
        history: List[Dict[str, Any]],
        query_types: List[str]
    ) -> Optional[ChatResponse]:
        """
        Returns a ChatResponse, or None when the record could not be
        resolved so the caller can fall back to the knowledge base.
        """

        try:
            context = self.employee_context_provider.build_context(
                principal,
                query_types
            )

        except AuthenticationError:
            # A dead token must surface as a 401, not as an answer.
            raise

        except UpstreamUnavailableError as error:

            logger.warning(
                "HR gateway unavailable for employee=%s: %s",
                mask_employee(principal.employee_id),
                error.detail or error.message
            )

            return ChatResponse(
                answer=UPSTREAM_DOWN_MESSAGE,
                source_documents=[],
                llm_response=None,
                guardrail_status="upstream_unavailable",
                guardrail_reason="HR system did not respond"
            )

        except AppError as error:

            logger.error(
                "Could not build the employee context for "
                "employee=%s: %s",
                mask_employee(principal.employee_id),
                error.detail or error.message
            )

            return ChatResponse(
                answer=error.message,
                source_documents=[],
                llm_response=None,
                guardrail_status="error",
                guardrail_reason="Employee context unavailable"
            )

        if not context or not context.get("found"):

            logger.info(
                "No HR record resolved for employee=%s; falling back "
                "to the knowledge base",
                mask_employee(principal.employee_id)
            )

            return None

        log_personal(
            logger,
            "Employee context for %s:\n%s",
            principal.employee_id,
            context["text"]
        )

        # Pull policy documents too, so hybrid questions work:
        # "how many leaves are left and what is the policy?"
        documents = []

        try:
            documents = self._retrieve(
                self._translate(search_question)
            )

        except Exception as error:

            logger.warning(
                "Policy retrieval skipped for an employee question: "
                "%s: %s",
                type(error).__name__,
                error
            )

        messages = self.prompt_builder.build_employee_messages(
            question=question,
            employee_context=context["text"],
            documents=documents,
            history=history,
            language=language,
            employee_name=principal.employee_name
        )

        return self._generate_and_guard(
            messages=messages,
            question=question,
            principal=principal,
            memory_key=memory_key,
            language=language,
            documents=documents,
            guardrail_reason=(
                "Answered from the authenticated employee's own "
                "HR record"
            )
        )

    # ==============================================================
    # Generation
    # ==============================================================

    def _generate_and_guard(
        self,
        messages: List[Dict[str, str]],
        question: str,
        principal: Principal,
        memory_key: str,
        language: str,
        documents: list,
        guardrail_reason: str
    ) -> ChatResponse:

        try:
            llm_response = self.llm.generate(messages)

        except Exception as error:

            logger.error(
                "LLM generation failed for employee=%s: %s: %s",
                mask_employee(principal.employee_id),
                type(error).__name__,
                error
            )

            return ChatResponse(
                answer=GENERIC_FAILURE_MESSAGE,
                source_documents=documents,
                llm_response=None,
                guardrail_status="error",
                guardrail_reason="Answer generation failed"
            )

        raw_answer = (llm_response.content or "").strip()

        verdict = self.output_guard.check(
            answer=raw_answer,
            employee_id=principal.employee_id,
            question=question
        )

        answer = verdict.answer

        status = "allow"

        reason = guardrail_reason

        if verdict.blocked:
            status = "output_blocked"
            reason = verdict.reason or "Blocked by the output guard"

        elif verdict.modified:
            reason = f"{guardrail_reason} (identifiers masked)"

        self._remember(
            principal.employee_id,
            memory_key,
            question,
            answer,
            language
        )

        log_personal(logger, "Answer: %s", answer)

        return ChatResponse(
            answer=answer,
            source_documents=documents,
            llm_response=llm_response,
            guardrail_status=status,
            guardrail_reason=reason
        )

    # ==============================================================
    # Helpers
    # ==============================================================

    def _try_build_employee_context(
        self,
        principal: Principal,
        query_types: List[str]
    ) -> Optional[Dict[str, Any]]:
        """
        Best-effort variant used on the RAG path. A failure here
        must not cost the employee their policy answer.
        """

        try:
            return self.employee_context_provider.build_context(
                principal,
                query_types
            )

        except AuthenticationError:
            raise

        except Exception as error:

            logger.info(
                "Supporting employee context unavailable "
                "(%s); answering from policy only",
                type(error).__name__
            )

            return None

    def _translate(self, question: str) -> str:

        try:
            return (
                self.query_translator.translate_to_english(question)
                or question
            )

        except Exception as error:

            logger.warning(
                "Translation failed (%s); retrieving with the "
                "original text",
                type(error).__name__
            )

            return question

    def _retrieve(self, question: str) -> list:

        try:
            documents = self.retriever.retrieve(
                question,
                k=self.retrieval_top_k
            )

        except Exception as error:

            logger.error(
                "Retrieval failed: %s: %s",
                type(error).__name__,
                error
            )

            return []

        logger.debug("Retrieved %s document(s)", len(documents))

        return documents

    def _remember(
        self,
        employee_id: str,
        memory_key: str,
        question: str,
        answer: str,
        language: str
    ) -> None:

        try:
            self.memory_manager.add_user_message(
                user_id=employee_id,
                session_id=memory_key,
                content=question,
                language=language
            )

            self.memory_manager.add_assistant_message(
                user_id=employee_id,
                session_id=memory_key,
                content=answer,
                language=language
            )

        except Exception as error:

            # Losing history is annoying; failing the answer the
            # employee already waited for is worse.
            logger.error(
                "Could not persist conversation memory for "
                "employee=%s: %s: %s",
                mask_employee(employee_id),
                type(error).__name__,
                error
            )
