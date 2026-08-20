"""
Per-employee sliding-window rate limiter.

Two reasons this exists on an internal HR assistant:

  * every message costs an LLM call and up to three HR API calls,
    so a loop in a client can generate real load and real spend;
  * it bounds how fast a compromised account can be used to mine
    the knowledge base.

In-process, so the limit is per worker. WORKERS is documented as 1
for that reason; a multi-worker deployment needs a shared store.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Dict


@dataclass(frozen=True)
class RateLimitDecision:

    allowed: bool

    remaining: int

    retry_after_seconds: int = 0


class RateLimiter:

    def __init__(
        self,
        max_requests: int = 15,
        window_seconds: int = 60,
        max_tracked_users: int = 10_000
    ):

        self.max_requests = max(1, int(max_requests))
        self.window_seconds = max(1, int(window_seconds))
        self._max_tracked_users = max(1, int(max_tracked_users))

        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    # --------------------------------------------------------------

    def check(self, user_id: str) -> bool:
        """Boolean form, kept for existing call sites."""

        return self.evaluate(user_id).allowed

    def evaluate(self, user_id: str) -> RateLimitDecision:

        key = str(user_id or "anonymous").strip().casefold()

        now = time.monotonic()

        cutoff = now - self.window_seconds

        with self._lock:

            if (
                key not in self._hits
                and len(self._hits) >= self._max_tracked_users
            ):
                self._prune(cutoff)

            hits = self._hits[key]

            while hits and hits[0] < cutoff:
                hits.popleft()

            if len(hits) >= self.max_requests:

                retry_after = max(
                    1,
                    int(self.window_seconds - (now - hits[0])) + 1
                )

                return RateLimitDecision(
                    allowed=False,
                    remaining=0,
                    retry_after_seconds=retry_after
                )

            hits.append(now)

            return RateLimitDecision(
                allowed=True,
                remaining=self.max_requests - len(hits)
            )

    def reset(self, user_id: str) -> None:

        key = str(user_id or "").strip().casefold()

        with self._lock:
            self._hits.pop(key, None)

    # --------------------------------------------------------------

    def _prune(self, cutoff: float) -> None:
        """Caller must hold the lock."""

        empty = [
            key
            for key, hits in self._hits.items()
            if not hits or hits[-1] < cutoff
        ]

        for key in empty:
            self._hits.pop(key, None)
