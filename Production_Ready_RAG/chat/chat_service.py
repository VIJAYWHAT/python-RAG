from llm.base_llm import BaseLLM
from models.chat_response import ChatResponse

from guardrails.guardrail_result import GuardrailStatus
from guardrails.guardrail_logger import GuardrailLogger

from context_checker.context_checker import ContextChecker
from hr_queries.hr_query_store import HRQueryStore


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
        hr_query_store: HRQueryStore
    ):

        self.llm = llm
        self.retriever = retriever
        self.prompt_builder = prompt_builder

        self.memory_manager = memory_manager

        self.query_rewriter = query_rewriter

        self.guardrails = guardrails
        self.guardrail_logger = guardrail_logger

        self.context_checker = context_checker
        self.hr_query_store = hr_query_store

    def ask(
        self,
        question: str,
        session_id: str = "default-session"
    ):

        # --------------------------------
        # 1. Get session-specific memory
        # --------------------------------

        memory = self.memory_manager.get_memory(
            session_id
        )

        history = memory.get_messages()

        # --------------------------------
        # 2. Prompt Injection Guardrail
        # --------------------------------

        injection_result = self.guardrails.check_injection(
            question
        )

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

        # --------------------------------
        # 3. Query Rewriting
        # --------------------------------

        if history:

            search_question = self.query_rewriter.rewrite(
                question,
                history
            )

        else:

            search_question = question

        # --------------------------------
        # 4. Scope Guardrail
        # --------------------------------

        scope_result = self.guardrails.check_scope(
            search_question
        )

        if scope_result.status != GuardrailStatus.ALLOW:

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

        # --------------------------------
        # 5. Retrieve Documents
        # --------------------------------

        documents = self.retriever.retrieve(
            search_question
        )

        # --------------------------------
        # 6. Check Context
        # --------------------------------

        answerable = self.context_checker.is_answerable(
            question=search_question,
            documents=documents
        )

        if not answerable:

            query_id = self.hr_query_store.save_query(
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

        # --------------------------------
        # 7. Build Prompt
        # --------------------------------

        messages = self.prompt_builder.build_messages(
            question,
            documents,
            history
        )

        # --------------------------------
        # 8. Generate Answer
        # --------------------------------

        llm_response = self.llm.generate(
            messages
        )

        # --------------------------------
        # 9. Save Conversation
        # --------------------------------

        memory.add_user_message(
            question
        )

        memory.add_assistant_message(
            llm_response.content
        )

        # --------------------------------
        # 10. Return Response
        # --------------------------------

        return ChatResponse(
            answer=llm_response.content,
            source_documents=documents,
            llm_response=llm_response,
            guardrail_status="allow",
            guardrail_reason="Request passed guardrails"
        )