"""Pydantic V2 models"""

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


def _clean_model_name(v: object) -> str:
    """Coerce anything Langfuse might send (None, '', whitespace, non-str) to a safe label."""
    if isinstance(v, str):
        v = v.strip()
        if v:
            return v
    return "unknown_model"


class CostMetric(BaseModel):

    model_name: str = Field(
        default="unknown_model",
        description="The name of the LLM model. Falls back to 'unknown_model' if missing/blank in telemetry.",
    )
    total_cost_usd: float = Field(ge=0)
    total_tokens: int = Field(ge=0)
    request_count: int = Field(ge=0)
    is_shadow_cost: bool = Field(
        default=False,
        description="True means actual billed cost is $0 (free tier) — estimate, not the real bill",
    )

    # mode="before" runs BEFORE type validation, so this catches None/blank/wrong-type
    # values from Langfuse before Pydantic ever gets a chance to reject them.
    @field_validator("model_name", mode="before")
    @classmethod
    def _default_model_name(cls, v: object) -> str:
        return _clean_model_name(v)

    @field_validator("total_cost_usd", "total_tokens", "request_count", mode="before")
    @classmethod
    def _default_zero(cls, v: object) -> object:
        return 0 if v is None else v


class CostComparison(BaseModel):

    period_start: datetime
    period_end: datetime
    total_tokens: int = Field(ge=0)
    query_count: int = Field(ge=0)
    gemini_cost_usd: float = Field(ge=0)
    gemini_is_shadow_cost: bool
    gpt4_equivalent_cost_usd: float = Field(ge=0)
    savings_usd: float
    savings_pct: float


class RoutingDecision(BaseModel):

    request_id: str
    timestamp: datetime
    model_selected: str
    routing_reason: str
    cost_usd: float = Field(ge=0)
    latency_ms: float = Field(ge=0)
    tokens_used: int = Field(default=0, ge=0)
    cache_hit: bool = Field(default=False)

    @field_validator("model_selected", mode="before")
    @classmethod
    def _default_model_selected(cls, v: object) -> str:
        return _clean_model_name(v)

    @field_validator("routing_reason", mode="before")
    @classmethod
    def _default_routing_reason(cls, v: object) -> str:
        if isinstance(v, str) and v.strip():
            return v
        return "n/a"

    @field_validator("request_id", mode="before")
    @classmethod
    def _default_request_id(cls, v: object) -> str:
        if isinstance(v, str) and v.strip():
            return v
        return "unknown"

    @field_validator("cost_usd", "latency_ms", "tokens_used", mode="before")
    @classmethod
    def _default_zero(cls, v: object) -> object:
        return 0 if v is None else v


class AuditLogEntry(BaseModel):

    request_id: str
    timestamp: datetime
    routing_decision: RoutingDecision
    masked_prompt_snippet: str = Field(max_length=80)

    @field_validator("request_id", mode="before")
    @classmethod
    def _default_request_id(cls, v: object) -> str:
        if isinstance(v, str) and v.strip():
            return v
        return "unknown"