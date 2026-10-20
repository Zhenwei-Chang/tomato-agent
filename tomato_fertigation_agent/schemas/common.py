from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Scope(str, Enum):
    plant = "plant"
    view = "view"
    group = "group"
    greenhouse = "greenhouse"
    treatment = "treatment"
    dataset = "dataset"
    knowledge = "knowledge"


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class ErrorCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DATA_NOT_FOUND = "DATA_NOT_FOUND"
    MODEL_NOT_AVAILABLE = "MODEL_NOT_AVAILABLE"
    UNSUPPORTED_SCOPE = "UNSUPPORTED_SCOPE"
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"
    NO_RELIABLE_CASES = "NO_RELIABLE_CASES"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class EvidenceItem(Contract):
    evidence_id: str
    source: str
    locator: str = ""
    content: str = ""
    score: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ToolMetadata(Contract):
    tool_name: str
    tool_version: str = "1.0.0"
    data_source: list[str] = Field(default_factory=list)
    model_version: str | None = None
    scope: Scope
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confidence: Confidence = Confidence.UNKNOWN
    confidence_reason: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    trace_id: str
    tool_call_id: str


class ToolError(Contract):
    code: ErrorCode
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ToolResult(Contract):
    status: Literal["success", "partial", "error"]
    data: dict[str, Any] = Field(default_factory=dict)
    metadata: ToolMetadata
    warnings: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    error: ToolError | None = None

    @model_validator(mode="after")
    def consistent_status(self):
        if (self.status == "error") != (self.error is not None):
            raise ValueError("error status requires error, other statuses forbid error")
        return self


class ToolFailure(Exception):
    def __init__(self, code: ErrorCode, message: str, **details):
        super().__init__(message)
        self.code, self.details = code, details
