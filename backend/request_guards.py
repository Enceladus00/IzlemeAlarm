"""Checks that run before routing, so they cost almost nothing to apply and also
cover requests that reach the API without passing through nginx."""

import jwt
from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.rate_limit import (
    ANONYMOUS_ADDRESS_RATE,
    TOO_MANY_REQUESTS_DETAIL,
    client_address,
    limiter,
)
from backend.security import decode_access_token


# nginx allows the same for uploads: the 5 MB CSV limit plus multipart overhead.
MAX_UPLOAD_BODY_BYTES = 6 * 1024 * 1024
MAX_BODY_BYTES = 1024 * 1024
BODY_TOO_LARGE_DETAIL = "Request body is too large."


def _has_valid_token(headers: Headers) -> bool:
    scheme, _, token = headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    try:
        decode_access_token(token)
    except jwt.PyJWTError:
        return False
    return True


class AnonymousAddressCapMiddleware:
    """Caps requests without a valid login per address. Requests with one are
    capped per user by get_current_user instead, so people sharing an office
    address do not use up each other's allowance."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or _has_valid_token(Headers(scope=scope)):
            await self.app(scope, receive, send)
            return
        key = f"anonymous:{client_address(Request(scope))}"
        decision = limiter.acquire(key, *ANONYMOUS_ADDRESS_RATE)
        if decision.allowed:
            await self.app(scope, receive, send)
            return
        response = JSONResponse(
            status_code=429,
            content={"detail": TOO_MANY_REQUESTS_DETAIL},
            headers={"Retry-After": str(decision.retry_after)},
        )
        await response(scope, receive, send)


class BodySizeLimitMiddleware:
    """Limits body size ahead of routing, so the limit holds before any form
    parsing or login check runs."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = MAX_UPLOAD_BODY_BYTES if scope["path"] == "/uploads" else MAX_BODY_BYTES
        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdecimal() and int(declared) > limit:
            response = JSONResponse(status_code=413, content={"detail": BODY_TOO_LARGE_DETAIL})
            await response(scope, receive, send)
            return

        # A chunked body declares no length, so it is counted as it arrives.
        received = 0

        async def receive_within_limit() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status_code=413, detail=BODY_TOO_LARGE_DETAIL)
            return message

        await self.app(scope, receive_within_limit, send)
