from __future__ import annotations

from enum import Enum
from typing import Any


class ProviderErrorCode(str, Enum):
    MISSING_CREDENTIALS = "MISSING_CREDENTIALS"
    AUTH_FAILED = "AUTH_FAILED"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    NETWORK_ERROR = "NETWORK_ERROR"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    PROVIDER_RATE_LIMIT = "PROVIDER_RATE_LIMIT"
    PROVIDER_REFUSAL = "PROVIDER_REFUSAL"
    PROVIDER_INCOMPLETE = "PROVIDER_INCOMPLETE"
    PROVIDER_FORMAT_ERROR = "PROVIDER_FORMAT_ERROR"
    PROVIDER_BUDGET_EXCEEDED = "PROVIDER_BUDGET_EXCEEDED"


class ProviderError(RuntimeError):
    def __init__(self, code: ProviderErrorCode, message: str, **details: Any):
        super().__init__(message)
        self.code = code
        self.details = details

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code.value, "message": str(self), "details": self.details}
