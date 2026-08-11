from memory.chat_memory import ChatMemory
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
        memory,
        query_rewriter,
        guardrails,
        guardrail_logger,
        context_checker,
        hr_query_store
    ):
        self.llm = llm
        self.retriever = retriever
        self.prompt_builder = prompt_builder
        self.llm = llm
        self.memory = memory
        self.query_rewriter = query_rewriter
        self.guardrails = guardrails
        self.guardrail_logger = guardrail_logger
        self.context_checker = context_checker
        self.hr_query_store = hr_query_store

    def ask(self, question: str):

        # --------------------------------
        # 1. Prompt Injection Guardrail
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
        # 2. Query Rewriting
        # --------------------------------

        search_question = self.query_rewriter.rewrite(
            question,
            self.memory.get_messages()
        )

        # --------------------------------
        # 3. Scope Guardrail
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
        # 4. Continue Existing RAG
        # --------------------------------

        # Previous conversation
        history = self.memory.get_messages()

        # Rewrite only when history exists
        if history:
            search_question = self.query_rewriter.rewrite(
                question,
                history
            )
        else:
            search_question = question

        # Retrieve documents
        documents = self.retriever.retrieve(
            search_question
        )

        answerable = self.context_checker.is_answerable(
            question=search_question,
            documents=documents
        )
        if not answerable:
            query_id = self.hr_query_store.save_query(
                question=question,
                session_id="demo-session"
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

        # Build messages using original question
        messages = self.prompt_builder.build_messages(
            question,
            documents,
            history
        )

        # Generate answer
        llm_response = self.llm.generate(messages)

        # Save conversation
        self.memory.add_user_message(question)
        self.memory.add_assistant_message(llm_response.content)


        return ChatResponse(
            answer=llm_response.content,
            source_documents=documents,
            llm_response=llm_response,
            guardrail_status="allow",
            guardrail_reason="Request passed guardrails"
        )