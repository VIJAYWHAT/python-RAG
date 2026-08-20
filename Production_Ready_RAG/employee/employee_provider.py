"""
One seam between the chat pipeline and wherever employee data lives.

Production reads the live Ejadah HR APIs. Offline development reads
the seeded SQLite file in data/hr_employee.db, so the RAG and
guardrail work can be done without a VPN into staging.

Both providers answer the same question - "what should the model be
told about the employee who is asking?" - and both take a verified
`Principal`. Neither accepts a bare employee id, so there is no
call site from which the wrong employee's data could be requested.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional, Protocol

from config.settings import settings
from core.logging_config import get_logger
from ejadah.identity_service import Principal


logger = get_logger(__name__)


class EmployeeContextProvider(Protocol):
    """Produces the employee block for the LLM prompt."""

    name: str

    def build_context(
        self,
        principal: Principal,
        query_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        ...

    def invalidate(self, employee_id: str) -> None:
        ...


# ==================================================================
# Production: live Ejadah HR APIs
# ==================================================================


class EjadahApiContextProvider:

    name = "ejadah_api"

    def __init__(self) -> None:

        # Imported lazily so `local_db` mode does not need httpx to
        # have reached the gateway.
        from ejadah.ejadah_context_builder import EjadahContextBuilder
        from ejadah.employee_service import get_employee_service

        self._service = get_employee_service()
        self._builder = EjadahContextBuilder()

    def build_context(
        self,
        principal: Principal,
        query_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:

        snapshot = self._service.get_snapshot(
            principal,
            topics=query_types
        )

        context = self._builder.build(snapshot, topics=query_types)

        context["employee_id"] = principal.employee_id
        context["source"] = self.name
        context["errors"] = dict(snapshot.errors)

        return context

    def invalidate(self, employee_id: str) -> None:

        self._service.invalidate(employee_id)


# ==================================================================
# Development: seeded SQLite
# ==================================================================


class LocalDbContextProvider:
    """
    Wraps the original demo path (EmployeeDataService +
    EmployeeContextBuilder) behind the same interface.

    Refuses to start when ENVIRONMENT=production, because serving
    seeded demo records as though they were an employee's real HR
    data would be worse than an outage.
    """

    name = "local_db"

    def __init__(self) -> None:

        if settings.is_production:

            raise RuntimeError(
                "EMPLOYEE_DATA_SOURCE=local_db is a development-only "
                "provider and must not run with "
                "ENVIRONMENT=production"
            )

        from employee.employee_context_builder import (
            EmployeeContextBuilder,
        )

        self._builder = EmployeeContextBuilder()

        logger.warning(
            "Employee data is being served from the local SQLite "
            "demo database (%s). This is NOT real HR data.",
            settings.local_employee_db_path
        )

    def build_context(
        self,
        principal: Principal,
        query_types: Optional[List[str]] = None
    ) -> Dict[str, Any]:

        context = self._builder.build(
            employee_id=principal.employee_id,
            query_types=query_types
        )

        context["source"] = self.name
        context.setdefault("errors", {})

        return context

    def invalidate(self, employee_id: str) -> None:  # noqa: ARG002

        # The local provider reads SQLite on every call.
        return None


# ==================================================================
# Factory
# ==================================================================

_provider: EmployeeContextProvider | None = None
_provider_lock = threading.Lock()


def get_employee_context_provider() -> EmployeeContextProvider:

    global _provider

    if _provider is None:

        with _provider_lock:

            if _provider is None:

                if settings.employee_data_source == "local_db":
                    _provider = LocalDbContextProvider()

                else:
                    _provider = EjadahApiContextProvider()

                logger.info(
                    "Employee context provider: %s",
                    _provider.name
                )

    return _provider
