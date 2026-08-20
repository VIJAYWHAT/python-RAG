"""
Interactive chat against the real pipeline, from a terminal.

    python -m tools.chat_cli <AccessToken> [EmployeeNumber]

Useful for tuning prompts, guardrails and retrieval without
rebuilding the Flutter app each time. It goes through exactly the
same `ChatService` the API does, including authentication - so it
cannot be used to read an employee's record without their token,
which is the point.

For offline work with no gateway access, set
`EMPLOYEE_DATA_SOURCE=local_db` and `ENVIRONMENT=local`, then pass
one of the seeded ids from data/hr_employee.db as the token; the
local provider ignores it.

Replaces the older root-level `test_chat.py` / `test_chat_new.py`,
which construct `ChatService` positionally and predate both the
authentication rework and several constructor arguments.
"""

from __future__ import annotations

import argparse
import sys

from api import container as container_module
from auth.auth_service import AuthService
from config.settings import settings
from core.errors import AppError
from core.logging_config import configure_logging
from session.session_manager import SessionManager


def main() -> int:

    parser = argparse.ArgumentParser(
        description="Chat with the HR assistant from the terminal"
    )

    parser.add_argument("token", help="An employee's Ejadah AccessToken")

    parser.add_argument("employee_id", nargs="?", help="Employee number")

    parser.add_argument(
        "--sources",
        action="store_true",
        help="Print the retrieved documents for each answer"
    )

    args = parser.parse_args()

    configure_logging()

    # ----------------------------------------------------------
    # Authenticate first: no principal, no conversation.
    # ----------------------------------------------------------

    try:
        principal = AuthService.authenticate_token(
            args.token,
            args.employee_id
        )

    except AppError as error:
        print(f"\nAuthentication failed: {error.message}")
        print(f"Detail: {error.detail}")
        print(
            "\nRun `python -m tools.verify_ejadah_connection "
            "<token> <employee>` to diagnose."
        )
        return 1

    deps = container_module.build()

    session_id = SessionManager.new_session_id(prefix="cli")

    print()
    print("=" * 70)
    print("Ejadah HR AI Assistant")
    print("=" * 70)
    print(f"Employee    : {principal.display_name} "
          f"({principal.employee_id})")
    print(f"Data source : {settings.employee_data_source}")
    print(f"Session     : {session_id}")
    print()
    print("Commands: /new (new thread), /exit")
    print("=" * 70)

    while True:

        try:
            question = input("\nYou : ").strip()

        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return 0

        if not question:
            continue

        if question.lower() in ("/exit", "exit", "quit"):
            print("Bye.")
            return 0

        if question.lower() == "/new":

            memory_key = SessionManager.scope(
                principal.employee_id,
                session_id
            )

            deps.memory_manager.clear_session(
                principal.employee_id,
                memory_key
            )

            session_id = SessionManager.new_session_id(prefix="cli")

            print(f"Started a new thread: {session_id}")
            continue

        try:
            response = deps.chat_service.ask(
                question=question,
                principal=principal,
                session_id=session_id
            )

        except AppError as error:
            print(f"\nError: {error.message}")
            continue

        print()
        print("-" * 70)
        print(response.answer)
        print("-" * 70)

        print(
            f"guardrail : {response.guardrail_status} "
            f"({response.guardrail_reason})"
        )

        if response.llm_response:
            print(
                f"tokens    : prompt="
                f"{response.llm_response.prompt_tokens} "
                f"completion="
                f"{response.llm_response.completion_tokens} "
                f"total={response.llm_response.total_tokens}"
            )
        else:
            print("tokens    : none (the LLM was not called)")

        if args.sources and response.source_documents:

            print("sources   :")

            for document in response.source_documents:
                print(
                    f"  - {document.metadata.get('source', 'unknown')} "
                    f"(distance="
                    f"{document.metadata.get('distance', '?')})"
                )


if __name__ == "__main__":
    sys.exit(main())
