"""src/middleware/auth.py — HTTP Bearer / API-Key authentication middleware."""

from __future__ import annotations

from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.config import settings
from src.middleware.rbac import ActorContext, set_current_actor


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Intercepts incoming HTTP requests to validate API keys / Bearer tokens."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Public endpoints that bypass authentication
        if path in ("/", "/health", "/metrics"):
            return await call_next(request)

        # Extract API Key from Authorization header or X-API-Key
        api_key: Optional[str] = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            api_key = auth_header.split(" ", 1)[1].strip()
        elif "x-api-key" in request.headers:
            api_key = request.headers.get("x-api-key", "").strip()

        if settings.auth_enabled:
            if not api_key:
                return JSONResponse(
                    {
                        "error": "Unauthorized",
                        "message": "Missing API Key. Provide via 'Authorization: Bearer <token>' or 'X-API-Key: <token>' header.",
                        "status_code": 401,
                    },
                    status_code=401,
                )

            key_info = settings.api_keys.get(api_key)
            if not key_info:
                return JSONResponse(
                    {
                        "error": "Forbidden",
                        "message": "Invalid API Key provided.",
                        "status_code": 403,
                    },
                    status_code=403,
                )

            # Establish per-request ActorContext
            actor = ActorContext(
                actor_id=key_info.actor_id,
                tenant_id=key_info.tenant_id,
                scopes=key_info.scopes,
                is_admin=key_info.is_admin,
                rate_limit_rpm=key_info.rate_limit_rpm,
            )
            set_current_actor(actor)
            request.state.actor = actor

        return await call_next(request)
