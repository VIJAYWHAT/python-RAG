import time
from collections import defaultdict


class RateLimiter:

    def __init__(
        self,
        max_requests: int = 10,
        window_seconds: int = 60
    ):

        self.max_requests = max_requests
        self.window_seconds = window_seconds

        self.requests = defaultdict(list)

    def check(
        self,
        user_id: str
    ) -> bool:

        now = time.time()

        request_times = self.requests[user_id]

        # Remove expired requests
        request_times[:] = [
            timestamp
            for timestamp in request_times
            if now - timestamp < self.window_seconds
        ]

        if len(request_times) >= self.max_requests:

            return False

        request_times.append(now)

        return True