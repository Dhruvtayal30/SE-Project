"""Structured errors. Every expected failure carries a machine-readable code, an HTTP status
and (where possible) source locations, so the API and UI can explain what went wrong."""

from __future__ import annotations

from typing import Any


class AnalysisError(Exception):
    """Base class for expected, user-facing failures."""

    status = 422
    code = "ANALYSIS_ERROR"

    def __init__(self, message: str, *, code: str | None = None, status: int | None = None,
                 locations: list[dict[str, Any]] | None = None, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status:
            self.status = status
        self.locations = locations or []
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        err: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.locations:
            err["locations"] = self.locations
        if self.details:
            err["details"] = self.details
        return {"ok": False, "error": err}


class RequestError(AnalysisError):
    """The HTTP request itself is malformed (400)."""

    status = 400
    code = "INVALID_REQUEST"


class SyntaxFailure(AnalysisError):
    code = "SYNTAX_ERROR"


class UnsupportedConstruct(AnalysisError):
    code = "UNSUPPORTED_CONSTRUCT"


class LimitExceeded(AnalysisError):
    code = "LIMIT_EXCEEDED"


class FunctionNotFound(AnalysisError):
    code = "FUNCTION_NOT_FOUND"
