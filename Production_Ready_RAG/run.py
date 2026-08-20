"""
Development / single-host launcher.

    python run.py

For a real deployment, run uvicorn (or gunicorn with the uvicorn
worker) behind a TLS-terminating reverse proxy instead:

    uvicorn api.main:socket_app --host 0.0.0.0 --port 8000

WORKERS stays at 1 by design: the rate limiter and the verified-token
cache live in process memory, so a second worker would double the
effective rate limit and halve the cache hit rate. Scale by putting
the whole service behind more than one instance only after moving
both to a shared store.
"""

import uvicorn

from config.settings import settings
from core.logging_config import configure_logging, get_logger


def main() -> None:

    configure_logging()

    logger = get_logger(__name__)

    if settings.workers > 1:

        logger.warning(
            "WORKERS=%s but the rate limiter and token cache are "
            "per-process. Expect the effective rate limit to be "
            "%s x %s requests per window.",
            settings.workers,
            settings.workers,
            settings.rate_limit_max_requests
        )

    uvicorn.run(
        "api.main:socket_app",
        host=settings.host,
        port=settings.port,
        reload=not settings.is_production,
        workers=1 if not settings.is_production else settings.workers,
        # log_config=None leaves the root logger alone so
        # configure_logging()'s formatter and token-redacting filter
        # stay in place. access_log=False because api.main logs one
        # line per request itself, with the employee id attached.
        log_config=None,
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips="*"
    )


if __name__ == "__main__":
    main()
