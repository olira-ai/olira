"""Typed exception hierarchy for the Olira SDK."""


class OliraError(Exception):
    """Base exception for all Olira SDK errors."""


class AuthError(OliraError):
    """Raised on 401 Unauthorized or 403 Forbidden — invalid or revoked API key."""


class RateLimitError(OliraError):
    """Raised on 429 Too Many Requests. Includes retry_after from Retry-After header."""

    def __init__(self, message: str, retry_after: int = 0) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ValidationError(OliraError):
    """Raised on 422 or client-side validation failure (malformed event, PII in patient_id, etc.)."""


class ServerError(OliraError):
    """Raised on 409 Conflict or 5xx server-side failure after retries exhausted."""

    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code


class NetworkError(OliraError):
    """Raised on connection timeout, DNS failure, or other network error after retries exhausted."""
