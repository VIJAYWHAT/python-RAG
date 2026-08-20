"""
Deployment diagnostic for the Ejadah HR gateway.

Run this FIRST on any new host, before pointing the app at it:

    python -m tools.verify_ejadah_connection <AccessToken> [EmployeeNumber]

Get a token by signing in on the app with a test account and reading
`AccessToken` out of its debug log, or from the `userLogin` response.

It answers the four questions that decide whether the assistant can
work at all on this host:

  1. Can we reach the gateway, and does the TLS handshake succeed?
     (The gateway needs legacy renegotiation, which OpenSSL 3 refuses
      by default - this is the single most common cause of "the
      chatbot cannot see my leave balance".)

  2. Does the token verify, and to which employee?

  3. Which identity verification layers are actually active? If the
     answer is "binding only", read the residual-risk note in
     ejadah/identity_service.py before going live.

  4. Which HR sections come back, and in what shape? Field names in
     the Oracle-backed responses vary between environments; this
     prints the keys so ejadah_context_builder.py can be checked
     against reality rather than against an assumption.

The token is never printed. Employee data is printed - run this on a
console you are happy to see HR details on, and against a test
account where possible.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Mapping

from config.settings import settings
from core.errors import AppError
from core.logging_config import configure_logging, mask_token
from ejadah.ejadah_client import get_ejadah_client
from ejadah.ejadah_context_builder import EjadahContextBuilder
from ejadah.employee_service import EjadahEmployeeService
from ejadah.identity_service import (
    _decode_jwt_claims,
    get_identity_service,
)


def _rule(title: str) -> None:

    print()
    print("=" * 68)
    print(title)
    print("=" * 68)


def _ok(message: str) -> None:
    print(f"  [ OK ]  {message}")


def _warn(message: str) -> None:
    print(f"  [WARN]  {message}")


def _fail(message: str) -> None:
    print(f"  [FAIL]  {message}")


def _keys(value: Any) -> str:

    if isinstance(value, Mapping):
        return ", ".join(sorted(str(key) for key in value))

    if isinstance(value, list) and value and isinstance(value[0], Mapping):
        return ", ".join(sorted(str(key) for key in value[0]))

    return f"<{type(value).__name__}>"


def main() -> int:

    parser = argparse.ArgumentParser(
        description="Check this host can talk to the Ejadah HR gateway"
    )

    parser.add_argument("token", help="An employee's Ejadah AccessToken")

    parser.add_argument(
        "employee_id",
        nargs="?",
        help="The employee number that token belongs to. Required "
             "unless the token is a JWT carrying it, or "
             "EJADAH_IDENTITY_ROUTE is configured."
    )

    parser.add_argument(
        "--show-data",
        action="store_true",
        help="Also print the rendered prompt context. Contains real "
             "HR data."
    )

    args = parser.parse_args()

    configure_logging()

    # ==============================================================
    _rule("1. Configuration")
    # ==============================================================

    print(f"  Environment          : {settings.environment}")
    print(f"  Gateway              : {settings.ejadah_api_base_url}")
    print(f"  Verify SSL           : {settings.ejadah_verify_ssl}")
    print(f"  Legacy TLS reneg     : "
          f"{settings.ejadah_allow_legacy_tls_renegotiation}")
    print(f"  Employee data source : {settings.employee_data_source}")
    print(f"  Identity route       : "
          f"{settings.ejadah_identity_route or '(not configured)'}")
    print(f"  Token                : {mask_token(args.token)}")

    problems = settings.validate_for_production()

    if problems:
        for problem in problems:
            _warn(problem)
    else:
        _ok("No configuration problems")

    if settings.employee_data_source != "ejadah_api":
        _warn(
            "EMPLOYEE_DATA_SOURCE is not 'ejadah_api', so the running "
            "service would serve demo data even if these checks pass."
        )

    # ==============================================================
    _rule("2. Token format")
    # ==============================================================

    claims = _decode_jwt_claims(args.token)

    if claims:
        _ok("The token is a JWT.")

        # Claim VALUES can be identifying, so only the names are
        # printed - that is all we need to configure the lookup.
        print(f"  Claim names: {', '.join(sorted(claims))}")

        _ok(
            "Identity can be bound cryptographically to the token "
            "(verification layer 1 is active)."
        )
    else:
        _warn(
            "The token is opaque, not a JWT, so verification layer 1 "
            "is unavailable."
        )

        if not settings.ejadah_identity_route:
            _warn(
                "EJADAH_IDENTITY_ROUTE is not set either. Identity "
                "therefore rests on the upstream echo check plus "
                "token binding - see the residual-risk note in "
                "ejadah/identity_service.py."
            )

    # ==============================================================
    _rule("3. Reachability and token verification")
    # ==============================================================

    try:
        get_ejadah_client()
        _ok("HTTP client built (TLS options applied).")

    except Exception as error:
        _fail(f"Could not build the HTTP client: {error}")
        return 1

    identity = get_identity_service()

    try:
        principal = identity.authenticate(
            token=args.token,
            claimed_employee_id=args.employee_id
        )

    except AppError as error:
        _fail(f"{type(error).__name__}: {error.detail or error.message}")

        print()
        print("  Common causes:")
        print("   * The token has expired, or a logout on another "
              "device revoked it.")
        print("   * EJADAH_API_BASE_URL points at the wrong "
              "environment for this token (staging token against "
              "live, or the reverse).")
        print("   * TLS handshake failure. If the error mentions "
              "'unsafe legacy renegotiation', confirm "
              "EJADAH_ALLOW_LEGACY_TLS_RENEGOTIATION=true.")
        print("   * The employee number was not supplied and the "
              "token carries no claim to look one up with.")

        return 1

    except Exception as error:
        _fail(f"Unexpected: {type(error).__name__}: {error}")
        return 1

    _ok(f"Token verified. Employee: {principal.employee_id}")

    print(f"  Name        : {principal.display_name}")
    print(f"  Designation : {principal.designation or '-'}")
    print(f"  Department  : {principal.department or '-'}")
    print(f"  Verified by : {' + '.join(principal.verified_by)}")

    if principal.verified_by == ("upstream",):
        _warn(
            "Only the upstream echo check ran. A gateway that does "
            "not itself check the body's EmployeeNumber against the "
            "bearer token would not be caught by this layer alone."
        )

    # ==============================================================
    _rule("4. HR sections")
    # ==============================================================

    service = EjadahEmployeeService()

    checks = (
        ("Profile", lambda: service.get_profile(principal)),
        ("Leave balance", lambda: service.get_leave_balance(principal)),
        ("Leave history", lambda: service.get_leave_history(principal)),
        ("Letter requests", lambda: service.get_letters(principal)),
    )

    for label, call in checks:

        try:
            value = call()

        except AppError as error:
            _fail(f"{label}: {error.detail or error.message}")
            continue

        except Exception as error:
            _fail(f"{label}: {type(error).__name__}: {error}")
            continue

        if value is None:
            _warn(f"{label}: the gateway returned nothing")
            continue

        if isinstance(value, list):
            _ok(f"{label}: {len(value)} row(s)")

            if value:
                print(f"          fields: {_keys(value)}")

        elif isinstance(value, Mapping):
            _ok(f"{label}: 1 record")
            print(f"          fields: {_keys(value)}")

        else:
            _ok(f"{label}: {value}")

    # ==============================================================
    _rule("5. Prompt context")
    # ==============================================================

    snapshot = service.get_snapshot(
        principal,
        topics=[
            "profile",
            "leave_balance",
            "leave_history",
            "letters",
        ]
    )

    context = EjadahContextBuilder().build(
        snapshot,
        topics=["profile", "leave_balance", "leave_history", "letters"]
    )

    if not context["found"]:
        _fail("No employee record resolved; the assistant would fall "
              "back to policy-only answers.")
        return 1

    _ok(f"Context built. Sections: {', '.join(context['sections'])}")
    print(f"  Length: {len(context['text'])} characters")

    if snapshot.errors:
        for section, message in snapshot.errors.items():
            _warn(f"Section '{section}' failed: {message}")

    if args.show_data:
        print()
        print("-" * 68)
        print(context["text"])
        print("-" * 68)
    else:
        print()
        print("  Re-run with --show-data to print the rendered "
              "context (contains real HR data).")

    _rule("Result")

    print("  The assistant can authenticate employees and read their "
          "HR records on this host.")

    if problems:
        print(f"  {len(problems)} configuration warning(s) above still "
              f"need attention before production.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
