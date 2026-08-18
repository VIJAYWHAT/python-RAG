from llm.base_llm import BaseLLM
from models.chat_response import ChatResponse

from guardrails.guardrail_result import GuardrailStatus
from guardrails.guardrail_logger import GuardrailLogger

from context_checker.context_checker import ContextChecker
from hr_queries.hr_query_store import HRQueryStore

from language.language_detector import LanguageDetector
from language.query_translator import QueryTranslator
from employee.employee_query_detector import (
    EmployeeQueryDetector
)

from employee.employee_context_builder import (
    EmployeeContextBuilder
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
        query_translator: QueryTranslator
    ):

        self.llm = llm
        self.retriever = retriever
        self.prompt_builder = prompt_builder
        self.employee_context_builder = (EmployeeContextBuilder())

        # Persistent conversation memory
        self.memory_manager = memory_manager

        self.query_rewriter = query_rewriter

        self.guardrails = guardrails
        self.guardrail_logger = guardrail_logger

        self.context_checker = context_checker
        self.hr_query_store = hr_query_store

        self.language_detector = language_detector
        self.query_translator = query_translator

    def ask(
        self,
        question: str,
        user_id: str,
        session_id: str = "default-session"
    ):
        query_type = (
            EmployeeQueryDetector.get_query_type(
                question
            )
        )

        is_employee_query = (
            EmployeeQueryDetector.is_employee_query(
                question
            )
        )
        
        if is_employee_query:

            print("")
            print("========================================")
            print("[EMPLOYEE QUERY]")
            print("========================================")

            print(
                f"Employee ID : {user_id}"
            )

            print(
                f"Question    : {question}"
            )

            print(
                f"Query Type  : {query_type}"
            )

            employee_context = (
                self.employee_context_builder.build(
                    employee_id=user_id,
                    query_type=query_type
                )
            )

            print(
                f"Employee Context: {employee_context}"
            )
        
        # --------------------------------
        # 1. Detect User Language
        # --------------------------------

        language = self.language_detector.detect_language(
            question
        )

        # --------------------------------
        # 2. Get Session-Specific Memory
        # --------------------------------

        history = self.memory_manager.get_messages(
            user_id=user_id,
            session_id=session_id
        )

        # --------------------------------
        # 3. Prompt Injection Guardrail
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
        # 4. General Conversation
        # --------------------------------

        general_result = (
            self.guardrails.check_general_conversation(
                question
            )
        )

        if general_result.message:

            print(
                f"[GENERAL CHAT] "
                f"Question={question} | "
                f"Reason={general_result.reason}"
            )

            self.memory_manager.add_user_message(
                user_id=user_id,
                session_id=session_id,
                content=question,
                language=language
            )

            self.memory_manager.add_assistant_message(
                user_id=user_id,
                session_id=session_id,
                content=general_result.message,
                language=language
            )

            return ChatResponse(
                answer=general_result.message,
                source_documents=[],
                llm_response=None,
                guardrail_status="greeting",
                guardrail_reason=general_result.reason
            )
            
        # --------------------------------
        # 4. Query Rewriting
        # --------------------------------

        if history:

            search_question = self.query_rewriter.rewrite(
                question,
                history
            )
            
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

        else:

            search_question = question

        # --------------------------------
        # 5. Scope Guardrail
        # --------------------------------

        scope_result = self.guardrails.check_scope(
            search_question
        )

        # --------------------------------
        # Handle Greeting
        # --------------------------------

        if scope_result.status == GuardrailStatus.GREETING:

            greeting_message = (
                "Hi! How can I help you with your HR-related questions?"
            )

            # Save greeting in conversation memory
            self.memory_manager.add_user_message(
                user_id=user_id,
                session_id=session_id,
                content=question,
                language=language
            )

            self.memory_manager.add_assistant_message(
                user_id=user_id,
                session_id=session_id,
                content=greeting_message,
                language=language
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


        # --------------------------------
        # Handle Out Of Scope
        # --------------------------------

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

        # --------------------------------
        # 6. Translate Query for Retrieval
        # --------------------------------

        retrieval_question = (
            self.query_translator.translate_to_english(
                search_question
            )
        )
        print("\n========================================")
        print("[RETRIEVAL DEBUG]")
        print("========================================")
        print(f"Original Question  : {question}")
        print(f"Search Question    : {search_question}")
        print(f"Retrieval Question : {retrieval_question}")
        print("========================================\n")

        # --------------------------------
        # 7. Retrieve Documents
        # --------------------------------

        documents = self.retriever.retrieve(
            retrieval_question
        )
        print("\n========================================")
        print("[RAG DEBUG]")
        print("========================================")
        print(f"Question          : {question}")
        print(f"Retrieved Docs    : {len(documents)}")

        for index, document in enumerate(documents):
            print(
                f"Document {index + 1}: "
                f"{document}"
            )

        print("========================================\n")

        # --------------------------------
        # 8. Check Context
        # --------------------------------

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

        # --------------------------------
        # 9. Build Prompt
        # --------------------------------
        #
        # IMPORTANT:
        # Use the ORIGINAL question here so the LLM
        # can answer in the user's language.
        #

        messages = self.prompt_builder.build_messages(
            question,
            documents,
            history,
            language
        )

        # --------------------------------
        # 10. Generate Answer
        # --------------------------------

        llm_response = self.llm.generate(
            messages
        )

        # --------------------------------
        # 11. Save User Message
        # --------------------------------

        self.memory_manager.add_user_message(
            user_id=user_id,
            session_id=session_id,
            content=question,
            language=language
        )

        # --------------------------------
        # 12. Save Assistant Message
        # --------------------------------

        self.memory_manager.add_assistant_message(
            user_id=user_id,
            session_id=session_id,
            content=llm_response.content,
            language=language
        )

        # --------------------------------
        # 13. Return Response
        # --------------------------------

        return ChatResponse(
            answer=llm_response.content,
            source_documents=documents,
            llm_response=llm_response,
            guardrail_status="allow",
            guardrail_reason="Request passed guardrails"
        )