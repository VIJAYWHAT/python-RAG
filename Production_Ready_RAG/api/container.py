"""
Wiring.

Everything expensive - the embedding model, the Chroma client, the
LLM clients - is built once here and shared. Building them per
request would add seconds of latency and re-download the sentence
transformer.

`build()` is called from the FastAPI lifespan hook so a failure
stops the process at startup rather than surfacing as a 500 on the
first employee's first message.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from api.rate_limiter import RateLimiter
from chat.chat_service import ChatService
from config.settings import settings
from context_checker.context_checker import ContextChecker
from core.logging_config import get_logger
from embeddings.embedding_model import EmbeddingModel
from employee.employee_provider import get_employee_context_provider
from guardrails.guardrail_logger import GuardrailLogger
from guardrails.guardrail_service import GuardrailService
from guardrails.output_guard import OutputGuard
from hr_queries.hr_query_store import HRQueryStore
from language.language_detector import LanguageDetector
from language.query_translator import QueryTranslator
from llm.groq_llm import GroqLLM
from memory.memory_manager import MemoryManager
from prompts.prompt_builder import PromptBuilder
from query_rewriter.query_rewriter import QueryRewriter
from retriever.retriever import Retriever
from vectordb.chroma_db import VectorDatabase


logger = get_logger(__name__)


@dataclass
class Container:

    chat_service: ChatService

    memory_manager: MemoryManager

    rate_limiter: RateLimiter

    employee_context_provider: object

    vector_db: VectorDatabase

    document_count: int = 0


_container: Optional[Container] = None
_lock = threading.Lock()


def build() -> Container:

    global _container

    if _container is not None:
        return _container

    with _lock:

        if _container is not None:
            return _container

        logger.info("Building application components...")

        # ----------------------------------------------------------
        # Retrieval
        # ----------------------------------------------------------

        embedding_model = EmbeddingModel(
            model_name=settings.embedding_model_name
        )

        vector_db = VectorDatabase(
            persist_directory=settings.vector_db_path,
            collection_name=settings.vector_db_collection
        )

        retriever = Retriever(
            embedding_model=embedding_model,
            vector_db=vector_db
        )

        document_count = 0

        try:
            document_count = vector_db.collection.count()

        except Exception as error:

            logger.warning(
                "Could not count the vector collection: %s",
                error
            )

        if document_count == 0:

            logger.warning(
                "The vector store '%s' is EMPTY. Policy questions "
                "will all answer 'not in the knowledge base' until "
                "ingestion has been run: "
                "python -m ingestion.ingest_knowledge_base",
                settings.vector_db_collection
            )

        else:
            logger.info(
                "Vector store ready | collection=%s chunks=%s",
                settings.vector_db_collection,
                document_count
            )

        # ----------------------------------------------------------
        # LLMs
        #
        # Two models: a small fast one for the classification and
        # rewriting steps, a larger one for the answer itself.
        # ----------------------------------------------------------

        rewrite_llm = GroqLLM(model=settings.groq_rewrite_model)

        answer_llm = GroqLLM(model=settings.groq_answer_model)

        # ----------------------------------------------------------
        # Pipeline pieces
        # ----------------------------------------------------------

        memory_manager = MemoryManager(
            database_path=settings.chat_memory_db_path
        )

        purged = memory_manager.purge_older_than(
            settings.memory_retention_days
        )

        if purged:
            logger.info(
                "Purged %s chat message(s) older than %s days",
                purged,
                settings.memory_retention_days
            )

        chat_service = ChatService(
            retriever=retriever,
            prompt_builder=PromptBuilder(),
            llm=answer_llm,
            memory_manager=memory_manager,
            query_rewriter=QueryRewriter(llm=rewrite_llm),
            guardrails=GuardrailService(scope_llm=rewrite_llm),
            guardrail_logger=GuardrailLogger(),
            context_checker=ContextChecker(llm=rewrite_llm),
            hr_query_store=HRQueryStore(
                db_path=settings.hr_query_db_path
            ),
            language_detector=LanguageDetector(),
            query_translator=QueryTranslator(llm=rewrite_llm),
            employee_context_provider=get_employee_context_provider(),
            output_guard=OutputGuard(),
            retrieval_top_k=settings.retrieval_top_k
        )

        _container = Container(
            chat_service=chat_service,
            memory_manager=memory_manager,
            rate_limiter=RateLimiter(
                max_requests=settings.rate_limit_max_requests,
                window_seconds=settings.rate_limit_window_seconds
            ),
            employee_context_provider=get_employee_context_provider(),
            vector_db=vector_db,
            document_count=document_count
        )

        logger.info("Application components ready.")

        return _container


def get_container() -> Container:

    if _container is None:
        return build()

    return _container


def reset() -> None:
    """Test helper."""

    global _container

    with _lock:
        _container = None
