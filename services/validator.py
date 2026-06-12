"""
Async bookmark link validator.

Architecture (per skills/async-validation.md):
  - Network I/O runs inside an isolated asyncio event loop created per-thread
    with asyncio.new_event_loop() — never sharing a loop with Flask's thread.
  - HEAD request first; fall back to GET on 405.
  - Results are collected in memory during the async phase, then written back
    to SQLite sequentially to avoid concurrent-write contention.
  - Background sweeper thread runs every 24 hours as a daemon.
"""

import asyncio
import threading
import time
from urllib.parse import urlparse

import aiohttp

from models.bookmark_db import (
    get_all_bookmarks_for_validation,
    get_user_bookmarks_for_validation,
    update_bookmark_status,
)

_SEMAPHORE_LIMIT = 50
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=5)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _map_status(http_code: int) -> str:
    """Map an HTTP status code to a bookmark health status per skill spec."""
    if 200 <= http_code < 400:
        return "active"
    if 400 <= http_code < 500:
        return "broken"
    return "warning"  # 500+


async def _check_url(session: aiohttp.ClientSession, url: str) -> str:
    """
    Return 'active', 'broken', or 'warning' for a single URL.
    Tries HEAD first; retries with GET on 405.
    Timeouts → 'broken'; network/other errors → 'warning'.
    Non-http/https URLs (e.g. javascript:, file:) are skipped as 'broken'.
    """
    if urlparse(url).scheme not in ("http", "https"):
        return "broken"
    try:
        async with session.head(
            url, timeout=_REQUEST_TIMEOUT, allow_redirects=True
        ) as resp:
            if resp.status == 405:
                raise _FallbackToGet()
            return _map_status(resp.status)
    except _FallbackToGet:
        pass
    except asyncio.TimeoutError:
        return "broken"
    except Exception:
        return "warning"

    # HEAD rejected — retry with GET
    try:
        async with session.get(
            url, timeout=_REQUEST_TIMEOUT, allow_redirects=True
        ) as resp:
            return _map_status(resp.status)
    except asyncio.TimeoutError:
        return "broken"
    except Exception:
        return "warning"


class _FallbackToGet(Exception):
    """Sentinel raised when HEAD returns 405 to trigger a GET retry."""


async def _validate_rows(rows: list[dict]) -> None:
    """
    Validate a list of {id, url} dicts concurrently, then write results
    back to SQLite sequentially after all network work is done.
    """
    if not rows:
        return

    semaphore = asyncio.Semaphore(_SEMAPHORE_LIMIT)
    results: dict[int, str] = {}

    async def _bounded_check(row: dict) -> None:
        async with semaphore:
            results[row["id"]] = await _check_url(session, row["url"])

    async with aiohttp.ClientSession(headers=_HEADERS) as session:
        await asyncio.gather(*(_bounded_check(row) for row in rows))

    # Sequential SQLite writes — safe after event loop work is complete
    for bookmark_id, status in results.items():
        update_bookmark_status(bookmark_id, status)


async def validate_user_bookmarks(user_id: int) -> None:
    """Validate all bookmarks owned by user_id."""
    await _validate_rows(get_user_bookmarks_for_validation(user_id))


async def validate_all_bookmarks() -> None:
    """Validate every bookmark in the database (all users)."""
    await _validate_rows(get_all_bookmarks_for_validation())


# ---------------------------------------------------------------------------
# Public sync entry-points (run async work in isolated event loops)
# ---------------------------------------------------------------------------

def _run_in_new_loop(coro) -> None:
    """Execute a coroutine in a brand-new event loop, then close it."""
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(coro)
    finally:
        loop.close()


def trigger_user_validation(user_id: int) -> None:
    """
    Spawn a daemon thread that immediately validates one user's bookmarks.
    Returns instantly — the caller should flash a message and redirect.
    """
    threading.Thread(
        target=_run_in_new_loop,
        args=(validate_user_bookmarks(user_id),),
        daemon=True,
        name=f"validate-user-{user_id}",
    ).start()


# ---------------------------------------------------------------------------
# Background sweeper — full DB pass every 24 hours
# ---------------------------------------------------------------------------

def _sweeper_loop() -> None:
    while True:
        try:
            _run_in_new_loop(validate_all_bookmarks())
        except Exception:
            pass  # never crash the daemon; next interval will retry
        time.sleep(24 * 60 * 60)


def start_background_validator() -> None:
    """Start the 24-hour sweeper daemon thread. Call once at app startup."""
    threading.Thread(
        target=_sweeper_loop,
        daemon=True,
        name="bookmark-validator-sweeper",
    ).start()
