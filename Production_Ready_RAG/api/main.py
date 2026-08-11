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

from api.schemas import (ChatRequest,ChatResponseSchema)
from auth.auth_service import (AuthService, security)
from fastapi import (FastAPI, Depends, HTTPException)
from fastapi import Request
from fastapi.responses import JSONResponse
from session.session_manager import SessionManager
from fastapi.middleware.cors import CORSMiddleware
from api.rate_limiter import RateLimiter
from language.language_detector import LanguageDetector
from language.query_translator import QueryTranslator

app = FastAPI(
    title="HR AI Chatbot API",
    description="RAG-based HR chatbot with guardrails",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173"
    ],
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["Authorization", "Content-Type"]
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


guardrails = GuardrailService(
    scope_llm=rewrite_llm
)
guardrail_logger = GuardrailLogger()


context_checker = ContextChecker(
    llm=rewrite_llm
)


hr_query_store = HRQueryStore()
memory_manager = MemoryManager()
rate_limiter = RateLimiter(
    max_requests=10,
    window_seconds=60
)
language_detector = LanguageDetector()
query_translator = QueryTranslator(
    llm=rewrite_llm
)

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
    hr_query_store=hr_query_store,
    language_detector=language_detector,
    query_translator=query_translator
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
    request: ChatRequest,
    credentials=Depends(security)
):

    # --------------------------------
    # 1. Authenticate user
    # --------------------------------

    user_id = AuthService.authenticate(
        credentials
    )
    if not rate_limiter.check(user_id):

        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later."
        )
    # --------------------------------
    # 2. Create user-scoped session
    # --------------------------------

    scoped_session_id = (
        SessionManager.get_scoped_session_id(
            user_id=user_id,
            session_id=request.session_id
        )
    )

    # --------------------------------
    # 3. Send request to ChatService
    # --------------------------------

    response = chat.ask(
        question=request.question,
        session_id=scoped_session_id
    )

    # --------------------------------
    # 4. Token information
    # --------------------------------

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

    # --------------------------------
    # 5. Return response
    # --------------------------------

    return ChatResponseSchema(
        answer=response.answer,
        session_id=request.session_id,
        guardrail_status=response.guardrail_status,
        guardrail_reason=response.guardrail_reason,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens
    )
    
@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception
):

    print(
        f"Unhandled error: {type(exc).__name__}: {exc}"
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred."
        }
    )