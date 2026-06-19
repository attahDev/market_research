import uuid
import logging
import time
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


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

    PUBLIC_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}

    async def dispatch(self, request: Request, call_next) -> Response:
        request.state.user_id = request.headers.get("X-User-ID")
        request.state.plan_tier = request.headers.get("X-Plan-Tier", "free")
        return await call_next(request)
