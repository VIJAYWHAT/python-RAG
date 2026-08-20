"""
A small thread-safe TTL cache.

Used for two things:

  * token -> verified identity     (identity_cache_ttl_seconds)
  * employee -> HR data snapshot   (employee_cache_ttl_seconds)

Both hold personal data, so entries expire quickly, the cache is
bounded, and `invalidate` is called on logout.

Deliberately dependency-free: a single API process does not need
Redis, and adding one would put employee records in a second
system that also has to be secured. If the service is ever scaled
to multiple workers, replace this with a shared cache and set
WORKERS accordingly.
"""

import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple


class TTLCache:

    def __init__(
        self,
        ttl_seconds: int,
        max_entries: int = 5000
    ):

        self._ttl = max(1, int(ttl_seconds))
        self._max_entries = max(1, int(max_entries))

        self._store: Dict[Any, Tuple[float, Any]] = {}
        self._lock = threading.RLock()

    # --------------------------------------------------------------

    def get(self, key: Any) -> Optional[Any]:

        now = time.monotonic()

        with self._lock:

            entry = self._store.get(key)

            if entry is None:
                return None

            expires_at, value = entry

            if expires_at <= now:
                self._store.pop(key, None)
                return None

            return value

    def set(self, key: Any, value: Any) -> None:

        now = time.monotonic()

        with self._lock:

            if len(self._store) >= self._max_entries:
                self._evict_expired(now)

            # Still full after pruning: drop the entry that expires
            # soonest so the cache stays bounded.
            if len(self._store) >= self._max_entries:

                oldest = min(
                    self._store.items(),
                    key=lambda item: item[1][0],
                    default=None
                )

                if oldest is not None:
                    self._store.pop(oldest[0], None)

            self._store[key] = (now + self._ttl, value)

    def get_or_set(
        self,
        key: Any,
        factory: Callable[[], Any]
    ) -> Any:
        """
        Note: `factory` runs outside the lock, so two concurrent
        misses may both call it. That is intentional - holding the
        lock across a network call would serialise every request.
        The upstream calls are idempotent reads.
        """

        cached = self.get(key)

        if cached is not None:
            return cached

        value = factory()

        if value is not None:
            self.set(key, value)

        return value

    def invalidate(self, key: Any) -> None:

        with self._lock:
            self._store.pop(key, None)

    def invalidate_matching(
        self,
        predicate: Callable[[Any, Any], bool]
    ) -> int:
        """
        Drops every entry whose (key, value) satisfies `predicate`.

        The predicate receives the stored value directly rather than
        looking it up again, so it cannot mutate the map while it is
        being scanned.
        """

        with self._lock:

            snapshot = list(self._store.items())

            doomed = [
                key
                for key, (_, value) in snapshot
                if predicate(key, value)
            ]

            for key in doomed:
                self._store.pop(key, None)

            return len(doomed)

    def clear(self) -> None:

        with self._lock:
            self._store.clear()

    def __len__(self) -> int:

        with self._lock:
            self._evict_expired(time.monotonic())
            return len(self._store)

    # --------------------------------------------------------------

    def _evict_expired(self, now: float) -> None:
        """Caller must hold the lock."""

        doomed = [
            key
            for key, (expires_at, _) in self._store.items()
            if expires_at <= now
        ]

        for key in doomed:
            self._store.pop(key, None)
