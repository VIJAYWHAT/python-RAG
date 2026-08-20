"""
HTTP client for the Ejadah HR API.

Contract (taken from the Flutter app's Apiservice.post_data):

    POST  {EJADAH_API_BASE_URL}<route>
    Headers:
        Content-Type  : application/json
        Accept        : application/json
        Authorization : Bearer <AccessToken>
    Body: {"EmployeeNumber": "..."} etc.

    200 OK, body:
        {
          "StatusCode":   200 | 401 | 406 | 500 | ...,
          "Response":     { ... },
          "ErrorMessage": "..."
        }

Note the envelope: the transport status is 200 even when the
business status says 401. Both are checked.

Two Ejadah-specific quirks are handled here:

1. Legacy TLS renegotiation. The gateway needs it; the Flutter app
   sets `allowLegacyUnsafeRenegotiation = true` in main.dart for the
   same reason. OpenSSL 3 refuses it unless we opt in, so without
   this every call fails at the handshake.

2. StatusCode 401/406 means "token no longer valid" - the app logs
   the user out on both. We translate them to AuthenticationError.
"""

from __future__ import annotations

import ssl
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

import httpx

from config.settings import settings
from core.errors import (
    AuthenticationError,
    UpstreamUnavailableError,
)
from core.logging_config import get_logger, mask_token
from ejadah.ejadah_routes import is_allowed


logger = get_logger(__name__)


# Business status codes that mean "this token is finished".
# Mirrors the Flutter app, which routes 401 and 406 to the login
# screen via Apiservice.post_data / post_data_list.
_TOKEN_REJECTED_CODES = {401, 406}


@dataclass(frozen=True)
class EjadahResponse:
    """A successful (StatusCode 200) envelope."""

    route: str

    status_code: int

    payload: Any

    raw: Dict[str, Any]

    def section(self, key: str, default=None):
        """
        Reads a key out of `Response` when it is an object.

        Ejadah wraps lists in a named key, for example
        `Response.EmployeeList` or `Response.LeaveHistoryRecord`.
        """

        if isinstance(self.payload, Mapping):
            return self.payload.get(key, default)

        return default


def _build_ssl_context() -> ssl.SSLContext | bool:
    """
    Returns the `verify` value for httpx.
    """

    if not settings.ejadah_verify_ssl:

        logger.warning(
            "EJADAH_VERIFY_SSL is disabled. Certificate validation "
            "is OFF - acceptable for a staging host only."
        )

        if not settings.ejadah_allow_legacy_tls_renegotiation:
            return False

        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    else:
        context = ssl.create_default_context()

    if settings.ejadah_allow_legacy_tls_renegotiation:

        # OP_LEGACY_SERVER_CONNECT. Named in Python 3.12+; fall back
        # to the raw OpenSSL bit on older builds.
        legacy_option = getattr(
            ssl,
            "OP_LEGACY_SERVER_CONNECT",
            0x4
        )

        context.options |= legacy_option

        # The gateway also negotiates older ciphers.
        try:
            context.set_ciphers("DEFAULT@SECLEVEL=1")

        except ssl.SSLError:
            logger.debug(
                "Could not lower the cipher security level; "
                "continuing with the default suite."
            )

    return context


class EjadahClient:
    """
    Thread-safe wrapper around a pooled httpx.Client.

    One instance is created at startup and shared. Tokens are never
    stored on the instance: every call takes the caller's token, so
    one employee's credentials can never be reused for another's
    request.
    """

    def __init__(self) -> None:

        self._lock = threading.Lock()

        self._client = httpx.Client(
            base_url=settings.ejadah_api_base_url,
            timeout=httpx.Timeout(
                settings.ejadah_api_timeout_seconds,
                connect=10.0
            ),
            verify=_build_ssl_context(),
            follow_redirects=False,
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10
            ),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Ejadah-HR-Assistant/1.0",
            }
        )

        logger.info(
            "Ejadah API client ready | base_url=%s verify_ssl=%s "
            "legacy_tls=%s",
            settings.ejadah_api_base_url,
            settings.ejadah_verify_ssl,
            settings.ejadah_allow_legacy_tls_renegotiation
        )

    # ==============================================================
    # Public API
    # ==============================================================

    def post(
        self,
        route: str,
        token: str,
        body: Optional[Dict[str, Any]] = None
    ) -> EjadahResponse:
        """
        Calls an allow-listed Ejadah route with the employee's own
        bearer token.

        Raises:
            AuthenticationError      - token rejected by Ejadah
            UpstreamUnavailableError - network / 5xx / bad envelope
        """

        if not is_allowed(route):

            # Defensive: a bug (or a prompt injection that reached
            # code generation) must not be able to call a mutating
            # HR endpoint.
            raise UpstreamUnavailableError(
                detail=(
                    f"Route '{route}' is not in the chatbot's "
                    f"read-only allow-list"
                )
            )

        if not token or not token.strip():
            raise AuthenticationError(detail="Empty bearer token")

        payload = dict(body or {})

        started = time.monotonic()

        response = self._request_with_retries(route, token, payload)

        elapsed_ms = (time.monotonic() - started) * 1000

        return self._parse_envelope(route, response, elapsed_ms, token)

    def close(self) -> None:

        with self._lock:
            self._client.close()

    # ==============================================================
    # Internals
    # ==============================================================

    def _request_with_retries(
        self,
        route: str,
        token: str,
        payload: Dict[str, Any]
    ) -> httpx.Response:

        attempts = max(1, settings.ejadah_api_max_retries + 1)

        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):

            try:

                response = self._client.post(
                    route,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"}
                )

                # Retry only on transient server-side failures.
                if response.status_code >= 500 and attempt < attempts:

                    logger.warning(
                        "Ejadah %s returned HTTP %s (attempt %s/%s); "
                        "retrying",
                        route,
                        response.status_code,
                        attempt,
                        attempts
                    )

                    time.sleep(0.4 * attempt)
                    continue

                return response

            except (httpx.TimeoutException, httpx.TransportError) as error:

                last_error = error

                if attempt < attempts:

                    logger.warning(
                        "Ejadah %s transport error (attempt %s/%s): "
                        "%s: %s",
                        route,
                        attempt,
                        attempts,
                        type(error).__name__,
                        error
                    )

                    time.sleep(0.4 * attempt)
                    continue

                break

        logger.error(
            "Ejadah %s unreachable after %s attempts: %s",
            route,
            attempts,
            last_error
        )

        raise UpstreamUnavailableError(
            detail=f"{route} unreachable: {last_error}"
        )

    def _parse_envelope(
        self,
        route: str,
        response: httpx.Response,
        elapsed_ms: float,
        token: str
    ) -> EjadahResponse:

        # --------------------------------------------------
        # Transport-level auth failure
        # --------------------------------------------------

        if response.status_code in _TOKEN_REJECTED_CODES:

            logger.info(
                "Ejadah %s rejected the token (HTTP %s) | token=%s",
                route,
                response.status_code,
                mask_token(token)
            )

            raise AuthenticationError(
                detail=f"{route} -> HTTP {response.status_code}"
            )

        if response.status_code != 200:

            logger.error(
                "Ejadah %s returned HTTP %s in %.0fms",
                route,
                response.status_code,
                elapsed_ms
            )

            raise UpstreamUnavailableError(
                detail=f"{route} -> HTTP {response.status_code}"
            )

        # --------------------------------------------------
        # Envelope
        # --------------------------------------------------

        try:
            envelope = response.json()

        except ValueError as error:

            logger.error(
                "Ejadah %s returned a non-JSON body: %s",
                route,
                error
            )

            raise UpstreamUnavailableError(
                detail=f"{route} -> invalid JSON"
            ) from error

        if not isinstance(envelope, Mapping):

            raise UpstreamUnavailableError(
                detail=f"{route} -> envelope is {type(envelope).__name__}"
            )

        business_status = envelope.get("StatusCode")

        try:
            business_status = int(business_status)

        except (TypeError, ValueError):
            business_status = None

        if business_status in _TOKEN_REJECTED_CODES:

            logger.info(
                "Ejadah %s rejected the token (StatusCode %s) | "
                "token=%s",
                route,
                business_status,
                mask_token(token)
            )

            raise AuthenticationError(
                detail=f"{route} -> StatusCode {business_status}"
            )

        if business_status != 200:

            # `ErrorMessage` comes from an internal system, so it is
            # logged but never returned to the client.
            logger.error(
                "Ejadah %s business failure | StatusCode=%s "
                "ErrorMessage=%s (%.0fms)",
                route,
                business_status,
                envelope.get("ErrorMessage"),
                elapsed_ms
            )

            raise UpstreamUnavailableError(
                detail=(
                    f"{route} -> StatusCode {business_status}: "
                    f"{envelope.get('ErrorMessage')}"
                )
            )

        logger.debug(
            "Ejadah %s ok in %.0fms",
            route,
            elapsed_ms
        )

        return EjadahResponse(
            route=route,
            status_code=business_status,
            payload=envelope.get("Response"),
            raw=dict(envelope)
        )


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_client: EjadahClient | None = None
_client_lock = threading.Lock()


def get_ejadah_client() -> EjadahClient:

    global _client

    if _client is None:

        with _client_lock:

            if _client is None:
                _client = EjadahClient()

    return _client


def close_ejadah_client() -> None:

    global _client

    with _client_lock:

        if _client is not None:
            _client.close()
            _client = None
