from datetime import datetime
from pydantic import BaseModel, Field


class CostMetric(BaseModel):
    model_name: str
    total_cost_usd: float = Field(ge=0)
    total_tokens: int = Field(ge=0)
    request_count: int = Field(ge=0)
    is_shadow_cost: bool = Field(
        default=False,
        description="True = actual cost is $0 (free tier). This is an estimate, not the actual bill.",
    )


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


class AuditLogEntry(BaseModel):
    request_id: str
    timestamp: datetime
    routing_decision: RoutingDecision
    masked_prompt_snippet: str = Field(max_length=80)