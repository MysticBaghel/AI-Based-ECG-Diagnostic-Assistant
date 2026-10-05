"""One error shape for the whole service.

Every failure - authentication, validation, a missing session, a bug - is the
same JSON object:

    {"detail": "human readable", "code": "machine_readable",
     "errors": [{"field": "value", "message": "..."}]}

`errors` is omitted when empty. Nothing in this service returns an HTML
traceback: a device that sends a malformed frame gets a status it can act on,
never a 500 it cannot.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def error_body(
    detail: str,
    code: str,
    errors: list[dict] | None = None,
) -> dict:
    body: dict = {"detail": detail, "code": code}
    if errors:
        body["errors"] = errors
    return body


class APIError(Exception):
    """Raised by dependencies and endpoints; converted by the handler below."""

    def __init__(
        self,
        status_code: int,
        detail: str,
        code: str,
        errors: list[dict] | None = None,
        headers: dict | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.code = code
        self.errors = errors or []
        self.headers = headers or {}


def _default_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "session_not_active",
        413: "payload_too_large",
        422: "validation_error",
        500: "internal_error",
    }.get(status_code, "error")


def _validation_errors(exc: RequestValidationError) -> list[dict]:
    """Turn pydantic's location tuples into a flat, documented list."""
    errors = []
    for item in exc.errors():
        location = ".".join(str(part) for part in item.get("loc", ()))
        errors.append(
            {
                "field": location or "body",
                "message": item.get("msg", "invalid value"),
            }
        )
    return errors


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.detail, exc.code, exc.errors),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                "Request body failed validation.",
                "validation_error",
                _validation_errors(exc),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(detail, _default_code(exc.status_code)),
            headers=getattr(exc, "headers", None) or {},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Last resort: still JSON. The traceback is logged by the server.
        return JSONResponse(
            status_code=500,
            content=error_body("Internal server error.", "internal_error"),
        )
