"""
Identity: who is actually asking?

This module is the security boundary of the whole service. Every
answer the assistant produces is scoped to the employee it returns,
so if this is wrong, one employee sees another's salary.

--------------------------------------------------------------------
THE RULE
--------------------------------------------------------------------
The employee number used for data access is the one THIS MODULE
returns. It is never the one in the chat payload, never one parsed
out of the user's message, and never one the LLM produced.
--------------------------------------------------------------------

How a token is verified
-----------------------
The Ejadah `AccessToken` is issued by `userLogin` and is what the
Flutter app already sends on every HR call. We accept the same
token and establish the caller's identity in three layers:

1. **Token claims.** If the token is a JWT, the employee identifier
   in its claims is authoritative. A client cannot change it
   without invalidating the signature, so a mismatch between the
   claim and what the client says it is, is a hard rejection.

2. **Live upstream verification.** The token is used to call
   Ejadah's own `getEmployeeInfo`. This proves the token is valid
   *right now* (not expired, not revoked by a logout on another
   device), and the employee number is then read out of the
   RESPONSE, not out of the request.

3. **Token binding.** The first identity a token resolves to is
   pinned to that token for the cache lifetime. If the same token
   later arrives claiming a different employee, that is treated as
   an attack and rejected.

Residual risk, stated plainly
-----------------------------
`getEmployeeInfo` takes an `EmployeeNumber` in its body. If the
Ejadah gateway does not itself check that the body's employee
belongs to the bearer token, then layer 2 cannot distinguish
"my record" from "someone else's record", and only layers 1 and 3
protect us. Closing that gap needs one of:

  * the token to be a JWT carrying the employee id (layer 1 then
    covers it outright); or
  * an Ejadah endpoint that resolves the caller from the token
    alone, e.g. `whoami` returning the owning EmployeeNumber -
    set EJADAH_IDENTITY_ROUTE to it and layer 2 becomes exact.

`identity_probe()` reports which layers are actually active on the
configured gateway; it runs at startup and logs a warning if the
deployment is relying on layer 3 alone.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional

from config.settings import settings
from core.errors import (
    AuthenticationError,
    AuthorizationError,
    EmployeeRecordNotFoundError,
)
from core.logging_config import get_logger, mask_employee, mask_token
from core.ttl_cache import TTLCache
from ejadah.ejadah_client import EjadahClient, get_ejadah_client
from ejadah.ejadah_routes import EjadahRoute


logger = get_logger(__name__)


# JWT claim names that may carry the employee identifier, in
# priority order. Ejadah's token format is not documented to us, so
# we look for the usual suspects rather than assuming one.
_EMPLOYEE_CLAIM_KEYS = (
    "EmployeeId",
    "EmployeeID",
    "employeeId",
    "employee_id",
    "EmployeeNumber",
    "employeeNumber",
    "employee_number",
    "EmpId",
    "empId",
    "sub",
    "unique_name",
    "nameid",
    "preferred_username",
)


@dataclass(frozen=True)
class Principal:
    """
    The verified caller.

    `employee_id` is the ONLY identifier the rest of the
    application may use to read HR data.
    """

    employee_id: str

    token: str = field(repr=False)

    employee_name: Optional[str] = None

    designation: Optional[str] = None

    department: Optional[str] = None

    # Which layers established this identity, for auditing.
    verified_by: tuple[str, ...] = ()

    verified_at: str = ""

    @property
    def display_name(self) -> str:

        if self.employee_name and self.employee_name.strip():
            return self.employee_name.strip()

        return self.employee_id

    def to_public_dict(self) -> Dict[str, Any]:
        """Safe to return over the wire. Never includes the token."""

        return {
            "employee_id": self.employee_id,
            "name": self.employee_name,
            "designation": self.designation,
            "department": self.department,
        }


def token_fingerprint(token: str) -> str:
    """
    A stable, non-reversible handle for a token.

    Used as the cache key so the cache never holds raw credentials,
    and as a correlation id in logs.
    """

    return hashlib.sha256(
        (token or "").strip().encode("utf-8")
    ).hexdigest()


# ==================================================================
# JWT claim reading (layer 1)
# ==================================================================


def _decode_jwt_claims(token: str) -> Optional[Dict[str, Any]]:
    """
    Reads the claim set out of a JWT *without verifying the
    signature*.

    That is safe for what we use it for and only for that: we never
    grant access on the strength of these claims. We use them in the
    one direction that cannot be abused - to REFUSE a request whose
    claimed employee disagrees with the token. An attacker who forges
    claims only locks themselves out; an attacker who replays a
    genuine token cannot change its claims.

    Returns None when the token is not a JWT.
    """

    token = (token or "").strip()

    parts = token.split(".")

    if len(parts) != 3:
        return None

    payload = parts[1]

    padding = "=" * (-len(payload) % 4)

    try:
        decoded = base64.urlsafe_b64decode(payload + padding)

    except (binascii.Error, ValueError):
        return None

    try:
        claims = json.loads(decoded)

    except (ValueError, UnicodeDecodeError):
        return None

    return claims if isinstance(claims, Mapping) else None


def _employee_from_claims(claims: Mapping[str, Any]) -> Optional[str]:

    for key in _EMPLOYEE_CLAIM_KEYS:

        value = claims.get(key)

        if value is None:
            continue

        value = str(value).strip()

        if value:
            return value

    return None


def _token_expiry(claims: Mapping[str, Any]) -> Optional[datetime]:

    raw = claims.get("exp")

    try:
        return datetime.fromtimestamp(int(raw), tz=timezone.utc)

    except (TypeError, ValueError):
        return None


# ==================================================================
# Identity service
# ==================================================================


class IdentityService:

    def __init__(self, client: Optional[EjadahClient] = None) -> None:

        self._client = client or get_ejadah_client()

        # fingerprint -> Principal
        self._cache = TTLCache(
            ttl_seconds=settings.identity_cache_ttl_seconds,
            max_entries=2000
        )

        self._probe_lock = threading.Lock()
        self._probe_result: Optional[Dict[str, Any]] = None

    # ==============================================================
    # Public API
    # ==============================================================

    def authenticate(
        self,
        token: str,
        claimed_employee_id: Optional[str] = None
    ) -> Principal:
        """
        Verifies `token` and returns the employee it belongs to.

        `claimed_employee_id` is what the client says it is. It is
        used only as a lookup hint for the upstream call and as
        something to CHECK - never as the answer.
        """

        token = (token or "").strip()

        if not token:
            raise AuthenticationError(detail="No token supplied")

        claim = (claimed_employee_id or "").strip() or None

        # Offline development. See _offline_principal for why this
        # cannot fire in production.
        offline = self._offline_principal(token, claim)

        if offline is not None:
            return offline

        fingerprint = token_fingerprint(token)

        # ----------------------------------------------------------
        # Layer 1: token claims
        # ----------------------------------------------------------

        claims = _decode_jwt_claims(token)

        claim_employee: Optional[str] = None

        if claims:

            claim_employee = _employee_from_claims(claims)

            expiry = _token_expiry(claims)

            if expiry and expiry <= datetime.now(timezone.utc):

                logger.info(
                    "Rejected an expired token | token=%s expired_at=%s",
                    mask_token(token),
                    expiry.isoformat()
                )

                self._cache.invalidate(fingerprint)

                raise AuthenticationError(
                    detail=f"Token expired at {expiry.isoformat()}"
                )

            if (
                claim_employee
                and claim
                and not _same_employee(claim_employee, claim)
            ):

                logger.warning(
                    "IDENTITY MISMATCH (token claim) | token=%s "
                    "claim_says=%s client_says=%s",
                    mask_token(token),
                    mask_employee(claim_employee),
                    mask_employee(claim)
                )

                raise AuthorizationError(
                    detail=(
                        "Client-supplied employee id does not match "
                        "the token's own claim"
                    )
                )

        # ----------------------------------------------------------
        # Layer 3: token binding (checked before the cache is used
        # as an answer, so a rebind attempt is caught even on a hit)
        # ----------------------------------------------------------

        cached = self._cache.get(fingerprint)

        if isinstance(cached, Principal):

            if claim and not _same_employee(cached.employee_id, claim):

                logger.warning(
                    "IDENTITY MISMATCH (token binding) | token=%s "
                    "bound_to=%s client_says=%s",
                    mask_token(token),
                    mask_employee(cached.employee_id),
                    mask_employee(claim)
                )

                raise AuthorizationError(
                    detail=(
                        "This token is already bound to a different "
                        "employee"
                    )
                )

            return cached

        # ----------------------------------------------------------
        # Layer 2: live upstream verification
        # ----------------------------------------------------------

        # 2a. Exact resolution, when the gateway offers it: ask
        #     Ejadah who the token belongs to, sending no employee
        #     id at all. Nothing the client said can influence the
        #     answer.
        token_owner = self._resolve_owner_from_token(token)

        if token_owner:

            if claim and not _same_employee(token_owner, claim):

                logger.warning(
                    "IDENTITY MISMATCH (token introspection) | "
                    "token=%s owner=%s client_says=%s",
                    mask_token(token),
                    mask_employee(token_owner),
                    mask_employee(claim)
                )

                raise AuthorizationError(
                    detail=(
                        "The HR system says this token belongs to a "
                        "different employee"
                    )
                )

            if (
                claim_employee
                and not _same_employee(token_owner, claim_employee)
            ):

                raise AuthorizationError(
                    detail=(
                        "Token claim disagrees with token "
                        "introspection"
                    )
                )

        lookup_id = token_owner or claim_employee or claim

        if not lookup_id:

            # Nothing to look up: the token is opaque and the client
            # sent no employee id. Refuse rather than guess.
            logger.info(
                "Cannot resolve an identity | token=%s "
                "(opaque token and no employee id supplied)",
                mask_token(token)
            )

            raise AuthenticationError(
                detail=(
                    "Token carries no employee claim and no employee "
                    "id was supplied"
                )
            )

        record = self._fetch_employee_record(token, lookup_id)

        upstream_id = _first_non_empty(
            record.get("EMPLOYEENUMBER"),
            record.get("EmployeeNumber"),
            record.get("EMPLOYEEID"),
            record.get("EmployeeId"),
        )

        if not upstream_id:

            logger.error(
                "Ejadah returned an employee record with no employee "
                "number | keys=%s",
                sorted(record.keys())
            )

            raise EmployeeRecordNotFoundError(
                detail="Employee record has no employee number"
            )

        # The upstream response wins. If it disagrees with what the
        # client claimed, the client was wrong (or lying).
        if claim and not _same_employee(upstream_id, claim):

            logger.warning(
                "IDENTITY MISMATCH (upstream echo) | token=%s "
                "upstream_says=%s client_says=%s",
                mask_token(token),
                mask_employee(upstream_id),
                mask_employee(claim)
            )

            raise AuthorizationError(
                detail=(
                    "The HR system resolved this token to a different "
                    "employee than the client claimed"
                )
            )

        if (
            claim_employee
            and not _same_employee(upstream_id, claim_employee)
        ):

            logger.warning(
                "IDENTITY MISMATCH (claim vs upstream) | token=%s "
                "claim_says=%s upstream_says=%s",
                mask_token(token),
                mask_employee(claim_employee),
                mask_employee(upstream_id)
            )

            raise AuthorizationError(
                detail="Token claim disagrees with the HR system"
            )

        verified_by: list[str] = ["upstream"]

        if token_owner:
            verified_by.insert(0, "token_introspection")

        if claim_employee:
            verified_by.insert(0, "token_claim")

        principal = Principal(
            employee_id=str(upstream_id).strip(),
            token=token,
            employee_name=_clean(
                _first_non_empty(
                    record.get("EMPLOYEENAME"),
                    record.get("EmployeeName"),
                )
            ),
            designation=_clean(
                _first_non_empty(
                    record.get("POS_SEG3"),
                    record.get("DESIGNATION"),
                    record.get("Designation"),
                )
            ),
            department=_clean(
                _first_non_empty(
                    record.get("DEPARTMENT"),
                    record.get("Department"),
                )
            ),
            verified_by=tuple(verified_by),
            verified_at=datetime.now(timezone.utc).isoformat()
        )

        self._cache.set(fingerprint, principal)

        logger.info(
            "Authenticated employee=%s via %s | token=%s",
            mask_employee(principal.employee_id),
            "+".join(verified_by),
            mask_token(token)
        )

        return principal

    def invalidate(self, token: str) -> None:
        """Called on logout, and whenever Ejadah rejects a token."""

        self._cache.invalidate(token_fingerprint(token))

    def invalidate_employee(self, employee_id: str) -> int:
        """Drops every cached token that resolves to this employee."""

        return self._cache.invalidate_matching(
            lambda _key, value: (
                isinstance(value, Principal)
                and _same_employee(value.employee_id, employee_id)
            )
        )

    # ==============================================================
    # Startup self-check
    # ==============================================================

    def identity_probe(self) -> Dict[str, Any]:
        """
        Reports which verification layers this deployment can rely
        on. Purely informational; safe to call at startup.
        """

        with self._probe_lock:
            return dict(self._ensure_probe())

    def note_token_format(self, token: str) -> None:
        """
        Records, once, whether real tokens are JWTs, and logs it so
        the operator knows whether verification layer 1 is actually
        protecting them.

        Called on every successful authentication, so it must be
        cheap and must never raise - an exception here would fail a
        login that has already succeeded.
        """

        with self._probe_lock:

            probe = self._ensure_probe()

            if probe.get("_format_logged"):
                return

            probe["_format_logged"] = True

            claims = _decode_jwt_claims(token)

            is_jwt_with_claim = bool(
                claims and _employee_from_claims(claims)
            )

            probe["token_claim_layer"] = (
                "active (JWT)"
                if is_jwt_with_claim
                else "unavailable (opaque token)"
            )

            has_introspection = bool(
                (settings.ejadah_identity_route or "").strip()
            )

        # Logging happens OUTSIDE the lock: a handler can block on a
        # file or a socket, and holding an authentication lock across
        # that would stall every concurrent login.
        if is_jwt_with_claim:

            logger.info(
                "Ejadah tokens are JWTs carrying an employee claim. "
                "Identity is cryptographically bound to the token."
            )

        elif has_introspection:

            logger.info(
                "Ejadah tokens are opaque, but EJADAH_IDENTITY_ROUTE "
                "is configured, so identity is resolved from the "
                "token alone."
            )

        else:

            logger.warning(
                "Ejadah tokens are opaque (not JWTs) and "
                "EJADAH_IDENTITY_ROUTE is not set, so identity rests "
                "on live upstream verification plus token binding. "
                "Ask the Ejadah team for an endpoint that resolves "
                "the caller from the token alone and set "
                "EJADAH_IDENTITY_ROUTE to make identity exact."
            )

    def _ensure_probe(self) -> Dict[str, Any]:
        """
        Returns the probe dict, creating it on first use.

        The caller MUST already hold `_probe_lock`. Keeping the
        creation here rather than in `identity_probe()` is what stops
        `note_token_format` from re-entering it: `_probe_lock` is a
        plain Lock, and one method calling the other while holding it
        deadlocked the first successful login of every process.
        """

        if self._probe_result is None:

            introspection = (settings.ejadah_identity_route or "").strip()

            self._probe_result = {
                "token_claim_layer": "unknown until first login",
                "token_introspection_layer": (
                    f"active ({introspection})"
                    if introspection
                    else "not configured"
                ),
                "upstream_layer": (
                    f"active ({EjadahRoute.GET_EMPLOYEE_INFO})"
                ),
                "binding_layer": "active",
            }

        return self._probe_result

    # ==============================================================
    # Internals
    # ==============================================================

    def _offline_principal(
        self,
        token: str,
        claim: Optional[str]
    ) -> Optional[Principal]:
        """
        Development-only shortcut so the RAG, prompt and guardrail
        work can be done without a route to the Ejadah gateway.

        Active ONLY when both of these hold:

          * ENVIRONMENT is not 'production'
          * EMPLOYEE_DATA_SOURCE is 'local_db'

        `local_db` is itself refused under ENVIRONMENT=production by
        `LocalDbContextProvider.__init__` and by
        `Settings.validate_for_production`, which refuses to start
        the app at all. So three independent checks stand between
        this code and a production deployment, and the guard below
        does not depend on either of the other two being reached.

        The "token" in this mode is just an employee id, optionally
        prefixed with `dev:`. It authenticates nothing - it selects
        which seeded record to read.
        """

        if settings.is_production:
            return None

        if settings.employee_data_source != "local_db":
            return None

        candidate = token

        if candidate.lower().startswith("dev:"):
            candidate = candidate[4:].strip()

        employee_id = candidate or claim

        if not employee_id:

            raise AuthenticationError(
                detail=(
                    "Offline mode: pass an employee id as the token, "
                    "e.g. 'dev:employee-001'"
                )
            )

        if claim and not _same_employee(employee_id, claim):

            raise AuthorizationError(
                detail=(
                    "Offline mode: token id and claimed id disagree"
                )
            )

        logger.warning(
            "OFFLINE IDENTITY: accepting employee=%s WITHOUT "
            "verification because EMPLOYEE_DATA_SOURCE=local_db and "
            "ENVIRONMENT=%s. Never valid in production.",
            mask_employee(employee_id),
            settings.environment
        )

        return Principal(
            employee_id=employee_id,
            token=token,
            employee_name=None,
            verified_by=("offline_dev",),
            verified_at=datetime.now(timezone.utc).isoformat()
        )

    def _resolve_owner_from_token(self, token: str) -> Optional[str]:
        """
        Asks the configured introspection route who this token
        belongs to, sending no employee id.

        Returns None when EJADAH_IDENTITY_ROUTE is not configured.
        A failure of the route itself is not fatal - we fall back to
        the other layers rather than locking every employee out
        because one endpoint is down.
        """

        route = (settings.ejadah_identity_route or "").strip()

        if not route:
            return None

        try:
            response = self._client.post(route, token=token, body={})

        except AuthenticationError:
            # A rejected token is a real answer: propagate it.
            raise

        except Exception as error:

            logger.error(
                "Identity route '%s' failed (%s: %s); falling back "
                "to the other verification layers",
                route,
                type(error).__name__,
                error
            )

            return None

        payload = response.payload

        if isinstance(payload, Mapping):

            for key in settings.ejadah_identity_response_keys:

                value = payload.get(key)

                if value is not None and str(value).strip():
                    return str(value).strip()

            # Some routes nest the record one level down.
            for nested_key in ("EmployeeList", "Employee", "User"):

                nested = payload.get(nested_key)

                if isinstance(nested, list) and nested:
                    nested = nested[0]

                if isinstance(nested, Mapping):

                    for key in settings.ejadah_identity_response_keys:

                        value = nested.get(key)

                        if value is not None and str(value).strip():
                            return str(value).strip()

        elif payload is not None and str(payload).strip():
            # A route that returns the bare employee number.
            return str(payload).strip()

        logger.error(
            "Identity route '%s' returned nothing recognisable; "
            "check EJADAH_IDENTITY_RESPONSE_KEYS",
            route
        )

        return None

    def _fetch_employee_record(
        self,
        token: str,
        employee_id: str
    ) -> Dict[str, Any]:

        response = self._client.post(
            EjadahRoute.GET_EMPLOYEE_INFO,
            token=token,
            body={"EmployeeNumber": str(employee_id)}
        )

        employees = response.section("EmployeeList")

        if not employees:

            logger.info(
                "Ejadah has no employee record for %s",
                mask_employee(employee_id)
            )

            raise EmployeeRecordNotFoundError(
                detail=f"getEmployeeInfo returned no rows for {employee_id}"
            )

        if isinstance(employees, Mapping):
            return dict(employees)

        first = employees[0]

        if not isinstance(first, Mapping):

            raise EmployeeRecordNotFoundError(
                detail=(
                    f"getEmployeeInfo returned "
                    f"{type(first).__name__} rows"
                )
            )

        return dict(first)


# ==================================================================
# Helpers
# ==================================================================


def _same_employee(left: Any, right: Any) -> bool:
    """
    Employee numbers arrive as "USE23120", "use23120" or 23120
    depending on the caller, so compare case-insensitively with
    surrounding whitespace removed.
    """

    return (
        str(left or "").strip().casefold()
        == str(right or "").strip().casefold()
    )


def _first_non_empty(*values):

    for value in values:

        if value is None:
            continue

        text = str(value).strip()

        if text and text.lower() not in ("null", "none"):
            return value

    return None


def _clean(value) -> Optional[str]:

    if value is None:
        return None

    text = str(value).strip()

    if not text or text.lower() in ("null", "none"):
        return None

    return text


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------

_identity_service: IdentityService | None = None
_identity_lock = threading.Lock()


def get_identity_service() -> IdentityService:

    global _identity_service

    if _identity_service is None:

        with _identity_lock:

            if _identity_service is None:
                _identity_service = IdentityService()

    return _identity_service
