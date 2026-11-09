"""Request limits, counted in this process's memory.

The API runs as one task with one worker, so one set of counters is enough; they
reset when the process restarts. Running several tasks would need shared storage,
otherwise each task would allow the full limit.
"""

import hashlib
import hmac
import ipaddress
import math
import os
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Request


LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_PAIR_LIMIT = 5  # failed logins for one account from one address
LOGIN_ADDRESS_LIMIT = 30  # failed logins from one address, whatever the account

# (requests, seconds), per user
GENERAL_RATE = (300, 60)
UPLOAD_RATE = (10, 60 * 60)
DEMO_SEED_RATE = (10, 60 * 60)
RULE_EVALUATION_RATE = (20, 60 * 60)

# Bounds memory if someone tries to create endless counters.
MAX_TRACKED_KEYS = 50_000


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after: int = 0
    # True only for the first refused request of a block, so that a block is
    # reported once rather than once per request.
    first_rejection: bool = False


@dataclass
class _Bucket:
    window: int
    hits: deque[float] = field(default_factory=deque)
    notified: bool = False


class SlidingWindowLimiter:
    def __init__(
        self,
        max_keys: int = MAX_TRACKED_KEYS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_keys = max_keys
        self._clock = clock
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()
        self._lock = threading.Lock()  # sync endpoints run in a thread pool

    def acquire(self, key: str, limit: int, window_seconds: int) -> Decision:
        with self._lock:
            now = self._clock()
            self._drop_expired(now)
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = self._buckets[key] = _Bucket(window_seconds)
                if len(self._buckets) > self._max_keys:
                    self._buckets.popitem(last=False)
            else:
                self._buckets.move_to_end(key)
            while bucket.hits and bucket.hits[0] <= now - window_seconds:
                bucket.hits.popleft()
            if len(bucket.hits) >= limit:
                first_rejection = not bucket.notified
                bucket.notified = True
                retry_after = max(1, math.ceil(bucket.hits[0] + window_seconds - now))
                return Decision(False, retry_after, first_rejection)
            bucket.notified = False
            bucket.hits.append(now)
            return Decision(True)

    def release(self, key: str) -> None:
        """Give back the most recent hit."""
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket and bucket.hits:
                bucket.hits.pop()

    def clear(self, key: str) -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    def _drop_expired(self, now: float) -> None:
        # Least recently used first, so this stops at the first live bucket.
        while self._buckets:
            bucket = next(iter(self._buckets.values()))
            if bucket.hits and bucket.hits[-1] + bucket.window > now:
                return
            self._buckets.popitem(last=False)


limiter = SlidingWindowLimiter()


def _valid_address(value: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address((value or "").strip()))
    except ValueError:
        return None


def client_address(request: Request) -> str:
    """The caller's address, in a form the caller cannot forge.

    Through the frontend, nginx states the real address and proves it with the
    shared secret. Otherwise the load balancer's own entry, the rightmost in
    X-Forwarded-For, is used; anything further left is caller-supplied.
    """
    secret = os.getenv("PROXY_SHARED_SECRET", "")
    supplied = request.headers.get("x-proxy-secret", "")
    if secret and hmac.compare_digest(secret.encode(), supplied.encode()):
        stated = _valid_address(request.headers.get("x-client-address"))
        if stated:
            return stated
    forwarded = request.headers.getlist("x-forwarded-for")
    rightmost = forwarded[-1].split(",")[-1] if forwarded else None
    return _valid_address(rightmost) or (request.client.host if request.client else "unknown")


@dataclass(frozen=True)
class LoginBlock:
    scope: str  # "account_address" or "address"
    retry_after: int
    first_rejection: bool


def _address_key(address: str) -> str:
    return f"login-address:{address}"


def _pair_key(address: str, username: str) -> str:
    # Hashed: users sometimes type their password into the username field.
    digest = hashlib.sha256(username.strip().casefold().encode()).hexdigest()
    return f"login-pair:{address}:{digest}"


def begin_login_attempt(address: str, username: str) -> LoginBlock | None:
    """Count an attempt before the costly password check; None means go ahead.

    Counting first also stops parallel guesses from all passing at once.
    """
    decision = limiter.acquire(_address_key(address), LOGIN_ADDRESS_LIMIT, LOGIN_WINDOW_SECONDS)
    if not decision.allowed:
        return LoginBlock("address", decision.retry_after, decision.first_rejection)
    decision = limiter.acquire(_pair_key(address, username), LOGIN_PAIR_LIMIT, LOGIN_WINDOW_SECONDS)
    if not decision.allowed:
        limiter.release(_address_key(address))
        return LoginBlock("account_address", decision.retry_after, decision.first_rejection)
    return None


def login_succeeded(address: str, username: str) -> None:
    # The address count only loses this attempt: logging in to one's own account
    # must not wipe earlier failures against other accounts.
    limiter.release(_address_key(address))
    limiter.clear(_pair_key(address, username))


def login_not_checked(address: str, username: str) -> None:
    """The password could not be checked (e.g. database down): not a failed guess."""
    limiter.release(_address_key(address))
    limiter.release(_pair_key(address, username))
