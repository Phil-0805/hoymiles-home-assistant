"""In-memory account session and conservative shared request pacing."""

import asyncio
from dataclasses import dataclass
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import hashlib
from time import monotonic

from .errors import HoymilesRateLimitError
from .telemetry import number


def retry_delay(value):
    """Parse Retry-After without shortening a server-directed account pause."""
    delay = number(value)
    if delay is None and isinstance(value, str):
        try:
            stamp = parsedate_to_datetime(value)
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=UTC)
            delay = (stamp - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            pass
    return max(60, delay or 60)


class AccountRuntime:
    """One token, login lock and request budget for identical account credentials.

    Keep at least one second between HTTP request starts and at most two HTTP
    requests in flight. These are conservative client limits, not a claim about
    Hoymiles' undocumented quota. Server Retry-After pauses every station using
    this account; per-station poll intervals still apply independently.
    """

    def __init__(self):
        self.token = None
        self.token_expires = datetime.min.replace(tzinfo=UTC)
        self.login_retry_at = datetime.min.replace(tzinfo=UTC)
        self.login_lock = asyncio.Lock()
        self._requests = asyncio.Semaphore(2)
        self._starts = asyncio.Lock()
        self._next_start = 0.0
        self._paused_until = 0.0

    def pause(self, seconds):
        self._paused_until = max(self._paused_until, monotonic() + seconds)

    @asynccontextmanager
    async def request(self):
        async with self._requests:
            async with self._starts:
                remaining = self._paused_until - monotonic()
                if remaining > 0:
                    raise HoymilesRateLimitError("Hoymiles requests are paused", remaining)
                delay = self._next_start - monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
                remaining = self._paused_until - monotonic()
                if remaining > 0:
                    raise HoymilesRateLimitError("Hoymiles requests are paused", remaining)
                self._next_start = monotonic() + 1.0
            yield


class AccountPool:
    """Reference-count sessions without putting credentials in dictionary keys."""

    def __init__(self):
        self._accounts: dict[str, _AccountRecord] = {}

    def acquire(self, username, password):
        key = hashlib.sha256(f"{username.casefold()}\0{password}".encode()).hexdigest()
        if key not in self._accounts:
            self._accounts[key] = _AccountRecord(AccountRuntime())
        record = self._accounts[key]
        record.references += 1
        return key, record.runtime

    def release(self, key):
        record = self._accounts.get(key)
        if record is not None:
            record.references -= 1
            if record.references == 0:
                del self._accounts[key]


@dataclass
class _AccountRecord:
    runtime: AccountRuntime
    references: int = 0
