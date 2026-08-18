import asyncio
import socketio

from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

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

from api.schemas import ChatRequest, ChatResponseSchema

from auth.auth_service import AuthService, security

from session.session_manager import SessionManager
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


sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*"
)

@sio.event
async def connect(sid, environ, auth):

    print("\n========================================")
    print("[SOCKET CONNECT]")
    print("========================================")

    print(f"Socket ID : {sid}")
    print(f"Auth      : {auth}")

    if not auth:

        print("[SOCKET AUTH] Missing authentication")

        return False

    token = auth.get("token")

    if not token:

        print("[SOCKET AUTH] Missing token")

        return False

    try:

        # TEMPORARY FOR DEMO
        # Replace with your real AuthService validation.

        user_id = AuthService.authenticate_token(
            token
        )

        print(
            f"[SOCKET AUTH] "
            f"Authenticated User: {user_id}"
        )

        await sio.save_session(
            sid,
            {
                "user_id": user_id
            }
        )

        return True

    except Exception as e:

        print(
            f"[SOCKET AUTH ERROR] "
            f"{type(e).__name__}: {e}"
        )

        return False

@sio.event
async def disconnect(sid):

    print("\n========================================")
    print("[SOCKET DISCONNECT]")
    print("========================================")

    print(
        f"Socket ID : {sid}"
    )
    
@sio.event
async def chat(sid, data):

    print("\n========================================")
    print("[SOCKET CHAT]")
    print("========================================")

    print(f"Socket ID : {sid}")
    print(f"Data      : {data}")

    try:

        # --------------------------------
        # Get authenticated socket session
        # --------------------------------

        session = await sio.get_session(sid)

        user_id = session.get("user_id")

        if not user_id:

            await sio.emit(
                "chat_error",
                {
                    "message": "User authentication failed."
                },
                to=sid
            )

            return

        # --------------------------------
        # Read request
        # --------------------------------

        question = data.get(
            "question",
            ""
        ).strip()

        session_id = data.get(
            "session_id",
            sid
        )

        if not question:

            await sio.emit(
                "chat_error",
                {
                    "message": "Question cannot be empty."
                },
                to=sid
            )

            return

        print(
            f"User ID    : {user_id}"
        )

        print(
            f"Question   : {question}"
        )

        print(
            f"Session ID : {session_id}"
        )

        # --------------------------------
        # Rate limiting
        # --------------------------------

        if not rate_limiter.check(user_id):

            await sio.emit(
                "chat_error",
                {
                    "message":
                    "Rate limit exceeded. Please try again later."
                },
                to=sid
            )

            return

        # --------------------------------
        # Process Chat
        # --------------------------------

        response = await asyncio.to_thread(
            chat.ask,
            question=question,
            user_id=user_id,
            session_id=session_id
        )

        # --------------------------------
        # Token information
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
        # Debug
        # --------------------------------

        print("\n========================================")
        print("[SOCKET RESPONSE]")
        print("========================================")

        print(
            f"User ID          : {user_id}"
        )

        print(
            f"Session ID       : {session_id}"
        )

        print(
            f"Question         : {question}"
        )

        print(
            f"Answer           : {response.answer}"
        )

        print(
            f"Guardrail Status : "
            f"{response.guardrail_status}"
        )

        print(
            f"Guardrail Reason : "
            f"{response.guardrail_reason}"
        )

        print(
            f"Prompt Tokens    : {prompt_tokens}"
        )

        print(
            f"Completion Tokens: {completion_tokens}"
        )

        print(
            f"Total Tokens     : {total_tokens}"
        )

        print("========================================")

        # --------------------------------
        # Send response to Flutter
        # --------------------------------

        await sio.emit(
            "chat_response",
            {
                "answer": response.answer,

                "session_id": session_id,

                "user_id": user_id,

                "guardrail_status":
                    response.guardrail_status,

                "guardrail_reason":
                    response.guardrail_reason,

                "prompt_tokens":
                    prompt_tokens,

                "completion_tokens":
                    completion_tokens,

                "total_tokens":
                    total_tokens
            },
            to=sid
        )

    except Exception as e:

        print(
            f"[SOCKET CHAT ERROR] "
            f"{type(e).__name__}: {e}"
        )

        await sio.emit(
            "chat_error",
            {
                "message":
                "Unable to process your request."
            },
            to=sid
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
    model="openai/gpt-oss-20b"
)


# Answer generation LLM
answer_llm = GroqLLM(
    model="openai/gpt-oss-120b"
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
# RAG TEST API
# --------------------------------------------------

@app.post("/api/rag-test")
def rag_test(
    request: ChatRequest,
    credentials=Depends(security)
):

    print("\n========================================")
    print("[RAG TEST API]")
    print("========================================")

    # --------------------------------
    # Authenticate user
    # --------------------------------

    user_id = AuthService.authenticate(
        credentials
    )

    print(f"User ID  : {user_id}")
    print(f"Question : {request.question}")
    print(f"Session  : {request.session_id}")

    # --------------------------------
    # Run complete ChatService
    # --------------------------------

    response = chat.ask(
        question=request.question,
        user_id=user_id,
        session_id=request.session_id
    )

    # --------------------------------
    # Extract retrieved documents
    # --------------------------------

    documents = []

    for index, document in enumerate(
        response.source_documents,
        start=1
    ):

        documents.append(
            {
                "document_number": index,
                "source": getattr(
                    document,
                    "source",
                    ""
                ),
                "content": getattr(
                    document,
                    "content",
                    ""
                )
            }
        )

    # --------------------------------
    # Token information
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
    # Debug output
    # --------------------------------

    print("\n[RAG TEST RESULT]")

    print(
        f"Guardrail Status : "
        f"{response.guardrail_status}"
    )

    print(
        f"Guardrail Reason : "
        f"{response.guardrail_reason}"
    )

    print(
        f"Retrieved Docs   : "
        f"{len(documents)}"
    )

    print(
        f"Answer           : "
        f"{response.answer}"
    )

    print(
        f"Prompt Tokens    : "
        f"{prompt_tokens}"
    )

    print(
        f"Completion Tokens: "
        f"{completion_tokens}"
    )

    print(
        f"Total Tokens     : "
        f"{total_tokens}"
    )

    print("========================================")

    # --------------------------------
    # Return debug response
    # --------------------------------

    return {
        "question": request.question,

        "session_id": request.session_id,

        "user_id": user_id,

        "answer": response.answer,

        "guardrail_status":
            response.guardrail_status,

        "guardrail_reason":
            response.guardrail_reason,

        "retrieved_document_count":
            len(documents),

        "retrieved_documents":
            documents,

        "prompt_tokens":
            prompt_tokens,

        "completion_tokens":
            completion_tokens,

        "total_tokens":
            total_tokens
    }


# --------------------------------------------------
# Chat API
# --------------------------------------------------

# @app.post(
#     "/api/chat",
#     response_model=ChatResponseSchema
# )
# def chat_endpoint(
#     request: ChatRequest,
#     credentials=Depends(security)
# ):

#     # --------------------------------
#     # 1. Authenticate user
#     # --------------------------------

#     user_id = AuthService.authenticate(
#         credentials
#     )
#     if not rate_limiter.check(user_id):

#         raise HTTPException(
#             status_code=429,
#             detail="Rate limit exceeded. Please try again later."
#         )
#     # --------------------------------
#     # 2. Create user-scoped session
#     # --------------------------------

#     scoped_session_id = (
#         SessionManager.get_scoped_session_id(
#             user_id=user_id,
#             session_id=request.session_id
#         )
#     )

#     # --------------------------------
#     # 3. Send request to ChatService
#     # --------------------------------

#     response = chat.ask(
#         question=request.question,
#         user_id=user_id,
#         session_id=request.session_id
#     )

#     # --------------------------------
#     # 4. Token information
#     # --------------------------------

#     prompt_tokens = None
#     completion_tokens = None
#     total_tokens = None

#     if response.llm_response:

#         prompt_tokens = (
#             response.llm_response.prompt_tokens
#         )

#         completion_tokens = (
#             response.llm_response.completion_tokens
#         )

#         total_tokens = (
#             response.llm_response.total_tokens
#         )

#     # --------------------------------
#     # 5. Return response
#     # --------------------------------

#     return ChatResponseSchema(
#         answer=response.answer,
#         session_id=request.session_id,
#         guardrail_status=response.guardrail_status,
#         guardrail_reason=response.guardrail_reason,
#         prompt_tokens=prompt_tokens,
#         completion_tokens=completion_tokens,
#         total_tokens=total_tokens
#     )
    
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
    
    
socket_app = socketio.ASGIApp(
    sio,
    app
)