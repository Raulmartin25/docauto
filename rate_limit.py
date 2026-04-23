"""
rate_limit.py
-------------
Per-IP rate limiting backed by Upstash Redis (REST API).

Fixed-window counter: key = ratelimit:<namespace>:<ip>, TTL = window.
On first hit the counter is created and its TTL is set (EXPIRE NX).
Subsequent hits only increment; the window expires naturally.

If Upstash credentials are missing (local dev without .env configured),
the check logs a warning and allows the request through so the app
still works during development.
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded, retry after {retry_after}s")


async def check_rate_limit(
    ip: str,
    limit: int,
    window_seconds: int,
    namespace: str = "process",
) -> None:
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

    if not url or not token:
        logger.warning("Upstash credentials missing — rate limiting disabled")
        return

    key = f"ratelimit:{namespace}:{ip}"

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{url}/pipeline",
                headers={"Authorization": f"Bearer {token}"},
                json=[
                    ["INCR", key],
                    ["EXPIRE", key, str(window_seconds), "NX"],
                    ["TTL", key],
                ],
            )
            resp.raise_for_status()
            results = resp.json()
    except httpx.HTTPError as exc:
        # Fail-open: if Upstash is unreachable, don't block real users.
        logger.error("Upstash request failed: %s — allowing request", exc)
        return

    count = results[0]["result"]
    ttl = results[2]["result"]

    if count > limit:
        raise RateLimitExceeded(retry_after=max(ttl, 1))
