from fastapi import FastAPI

from embeddings.embedding_model import EmbeddingModel
from vectordb.chroma_db import VectorDatabase
from retriever.retriever import Retriever
from prompts.prompt_builder import PromptBuilder

from llm.groq_llm import GroqLLM

from memory.chat_memory import ChatMemory

from chat.chat_service import ChatService

from query_rewriter.query_rewriter import QueryRewriter

from guardrails.guardrail_service import GuardrailService
from guardrails.guardrail_logger import GuardrailLogger

from context_checker.context_checker import ContextChecker

from hr_queries.hr_query_store import HRQueryStore
from memory.memory_manager import MemoryManager

from api.schemas import (
    ChatRequest,
    ChatResponseSchema
)


app = FastAPI(
    title="HR AI Chatbot API",
    description="RAG-based HR chatbot with guardrails",
    version="1.0.0"
)


# --------------------------------------------------
# Initialize Components
# --------------------------------------------------

embedding_model = EmbeddingModel()

vector_db = VectorDatabase()

retriever = Retriever(
    embedding_model=embedding_model,
    vector_db=vector_db
)

prompt_builder = PromptBuilder()


# Query rewriting LLM
rewrite_llm = GroqLLM(
    model="llama-3.1-8b-instant"
)


# Answer generation LLM
answer_llm = GroqLLM(
    model="llama-3.3-70b-versatile"
)


query_rewriter = QueryRewriter(
    llm=rewrite_llm
)


memory = ChatMemory()


guardrails = GuardrailService()

guardrail_logger = GuardrailLogger()


context_checker = ContextChecker(
    llm=rewrite_llm
)


hr_query_store = HRQueryStore()
memory_manager = MemoryManager()

# --------------------------------------------------
# Chat Service
# --------------------------------------------------

chat = ChatService(
    retriever=retriever,
    prompt_builder=prompt_builder,
    llm=answer_llm,
    memory_manager=memory_manager,
    query_rewriter=query_rewriter,
    guardrails=guardrails,
    guardrail_logger=guardrail_logger,
    context_checker=context_checker,
    hr_query_store=hr_query_store
)


# --------------------------------------------------
# Health Check
# --------------------------------------------------

@app.get("/health")
def health_check():

    return {
        "status": "ok",
        "service": "HR AI Chatbot"
    }


# --------------------------------------------------
# Chat API
# --------------------------------------------------

@app.post(
    "/api/chat",
    response_model=ChatResponseSchema
)
def chat_endpoint(
    request: ChatRequest
):

    response = chat.ask(
        question=request.question,
        session_id=request.session_id
    )

    prompt_tokens = None
    completion_tokens = None
    total_tokens = None

    if response.llm_response:

        prompt_tokens = (
            response.llm_response.prompt_tokens
        )

        completion_tokens = (
            response.llm_response.completion_tokens
        )

        total_tokens = (
            response.llm_response.total_tokens
        )

    return ChatResponseSchema(

        answer=response.answer,

        session_id=request.session_id,

        guardrail_status=response.guardrail_status,

        guardrail_reason=response.guardrail_reason,

        prompt_tokens=prompt_tokens,

        completion_tokens=completion_tokens,

        total_tokens=total_tokens
    )