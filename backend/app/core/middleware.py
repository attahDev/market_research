import uuid
import logging
import time
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger(__name__)

_ACTIVE_STATUSES = {"active", "trialing"}


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.monotonic()
        response = await call_next(request)
        duration_ms = int((time.monotonic() - start_time) * 1000)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = str(duration_ms)

        logger.info(
            f"method={request.method} path={request.url.path} "
            f"status={response.status_code} duration_ms={duration_ms} "
            f"request_id={request_id}"
        )
        return response


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Reads identity + subscription context from trusted headers, injected by
    the main GMBTE auth gateway after JWT verification.

    SECURITY FIX (mirrors proposal-builder's auth.py fix): the dev bypass
    fires ONLY when settings.app_env == "development" is explicitly set —
    never on a missing/unset config value. The old design pattern (bypass
    whenever some secret was merely unset) meant a missing env var in
    production silently granted unlimited access with zero auth. That
    footgun does not exist here: app_env defaults to "development" in this
    Settings class, so deployments MUST explicitly set APP_ENV=production
    for the real checks below to activate. Confirm this is set on Render.
    """

    PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        if settings.app_env == "development":
            request.state.user_id             = request.headers.get("X-User-ID", "dev-user")
            request.state.plan_tier           = request.headers.get("X-Plan-Tier", "founder_pro")
            request.state.subscription_status = "active"
            return await call_next(request)

        user_id = request.headers.get("X-User-ID")
        if not user_id:
            return JSONResponse(
                status_code=401,
                content={
                    "success": False,
                    "error": {
                        "code": "UNAUTHENTICATED",
                        "message": "Missing authentication headers. "
                                   "Requests must pass through the GMBTE auth gateway.",
                    },
                },
            )

        subscription_status = request.headers.get("X-Subscription-Status", "active")

        if subscription_status not in _ACTIVE_STATUSES:
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": {
                        "code": "SUBSCRIPTION_INACTIVE",
                        "message": f"Your subscription status ({subscription_status}) "
                                   f"does not allow tool access. Please update your billing details.",
                    },
                },
            )

        request.state.user_id             = user_id
        request.state.plan_tier           = request.headers.get("X-Plan-Tier", "explorer")
        request.state.subscription_status = subscription_status

        return await call_next(request)
