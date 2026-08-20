"""
Application entry point.

    uvicorn api.main:socket_app --host 0.0.0.0 --port 8000

`socket_app` is the ASGI app that serves both the REST routes and
the Socket.IO transport on the same port, which is what the Flutter
client expects.

Exception handling policy: no internal detail leaves this process.
Every handler logs the real cause and returns a fixed, safe message.
An HR assistant's stack traces would otherwise describe the HR
gateway, the vector store and the prompt structure to anyone who
can trigger an error.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

import socketio
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.gzip import GZipMiddleware

from api import container as container_module
from api.routes import auth_routes, chat_routes, health_routes
from api.socket_server import sio
from config.settings import settings
from core.errors import AppError
from core.logging_config import configure_logging, get_logger
from ejadah.ejadah_client import close_ejadah_client, get_ejadah_client


configure_logging()

logger = get_logger(__name__)


# ==================================================================
# Lifespan
# ==================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info(
        "Starting the Ejadah HR AI Assistant | environment=%s "
        "employee_data_source=%s",
        settings.environment,
        settings.employee_data_source
    )

    problems = settings.validate_for_production()

    if problems:

        for problem in problems:
            logger.error("CONFIGURATION: %s", problem)

        if settings.is_production:

            raise RuntimeError(
                "Refusing to start in production with an unsafe "
                "configuration: " + "; ".join(problems)
            )

        logger.warning(
            "Continuing despite %s configuration warning(s) because "
            "ENVIRONMENT is not 'production'.",
            len(problems)
        )

    # Fail fast: build the pipeline (embedding model, vector store,
    # LLM clients) before the port opens.
    get_ejadah_client()

    container_module.build()

    # Worth stating explicitly, because a Socket.IO handshake refused
    # on CORS grounds looks from the app like "the assistant will not
    # connect" with nothing in between to explain it.
    #
    # A client that sends NO Origin header - which is every native
    # mobile client, including the Flutter app's dart:io WebSocket -
    # is always allowed. This list only gates clients that do send
    # one: browsers (the Flutter web build) and some test tooling.
    logger.info(
        "Socket.IO origins: %s | REST CORS origins: %s "
        "(clients that send no Origin header, i.e. the mobile app, "
        "are always allowed)",
        settings.socket_cors_allow_origins or "<none>",
        settings.cors_allow_origins or "<none>"
    )

    logger.info(
        "Ready on %s:%s",
        settings.host,
        settings.port
    )

    try:
        yield

    finally:

        logger.info("Shutting down.")

        close_ejadah_client()


# ==================================================================
# App
# ==================================================================


app = FastAPI(
    title="Ejadah HR AI Assistant",
    description=(
        "RAG-based HR assistant for the Ejadah employee app.\n\n"
        "Authentication uses the employee's existing Ejadah "
        "`AccessToken` as a bearer token. Every answer is scoped to "
        "the employee that token belongs to."
    ),
    version=health_routes.SERVICE_VERSION,
    lifespan=lifespan,
    # The schema describes internal structure, so it is only served
    # outside production.
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json"
)


# ------------------------------------------------------------------
# Middleware
# ------------------------------------------------------------------

if settings.allowed_hosts and settings.allowed_hosts != ["*"]:

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.allowed_hosts
    )

app.add_middleware(
    CORSMiddleware,
    # The mobile app is not a browser, so CORS never applies to it.
    # This list is for the web build and local tooling only.
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Employee-Id",
        "X-Session-Id",
    ],
    max_age=600
)

app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def access_log(request: Request, call_next):
    """
    One line per request: method, path, status, duration and (once
    authenticated) the employee. Query strings are not logged - a
    mistyped client could put something sensitive there.
    """

    started = time.perf_counter()

    response = await call_next(request)

    duration_ms = (time.perf_counter() - started) * 1000

    employee = getattr(request.state, "employee_id", "-")

    logger.info(
        "%s %s -> %s | %.0fms | employee=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        employee
    )

    # Sensible defaults for a JSON API served over TLS.
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cache-Control", "no-store")

    return response


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

app.include_router(health_routes.router)
app.include_router(auth_routes.router)
app.include_router(chat_routes.router)


# ------------------------------------------------------------------
# Exception handlers
# ------------------------------------------------------------------


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):

    logger.warning(
        "%s on %s: %s",
        type(exc).__name__,
        request.url.path,
        exc.detail or exc.message
    )

    headers = (
        {"WWW-Authenticate": "Bearer"}
        if exc.status_code == 401
        else None
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
        headers=headers
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request,
    exc: RequestValidationError
):

    # Pydantic's default body echoes the input back, which for this
    # service means echoing the employee's question into an error
    # payload. Log it, return a fixed message.
    logger.info(
        "Validation failure on %s: %s",
        request.url.path,
        exc.errors()
    )

    return JSONResponse(
        status_code=422,
        content={
            "detail": (
                "The request could not be processed. Please check "
                "your question and try again."
            )
        }
    )


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(
    request: Request,
    exc: StarletteHTTPException
):

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None)
    )


@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception):

    logger.exception(
        "Unhandled %s on %s",
        type(exc).__name__,
        request.url.path
    )

    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."}
    )


# ------------------------------------------------------------------
# Combined ASGI app (REST + Socket.IO on one port)
# ------------------------------------------------------------------

socket_app = socketio.ASGIApp(sio, app)
