"""Langfuse Metrics API v2 + Observations API v2 wrapper — async-first.
"""

import re
from datetime import datetime, timezone

from langfuse import get_client

from config import settings
from schemas import AuditLogEntry, CostComparison, CostMetric, RoutingDecision

_PII_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"\b\d{10,}\b"),
]

_ZERO_COST_EPSILON = 1e-9


def _mask_pii(text: str) -> str:
    masked = text
    for pattern in _PII_PATTERNS:
        masked = pattern.sub("[REDACTED]", masked)
    return masked[:80]


def _split_tokens(total_tokens: int) -> tuple[int, int]:
    output_tokens = round(total_tokens * settings.assumed_output_token_ratio)
    input_tokens = total_tokens - output_tokens
    return input_tokens, output_tokens


def _price(input_tokens: int, output_tokens: int, input_rate: float, output_rate: float) -> float:
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate


async def fetch_cost_metrics(from_ts: datetime, to_ts: datetime) -> list[CostMetric]:
    langfuse = get_client()

    query = {
        "view": "observations",
        "metrics": [
            {"measure": "totalCost", "aggregation": "sum"},
            {"measure": "totalTokens", "aggregation": "sum"},
            {"measure": "count", "aggregation": "count"},
        ],
        "dimensions": [{"field": "providedModelName"}],
        "filters": [],
        "fromTimestamp": from_ts.isoformat(),
        "toTimestamp": to_ts.isoformat(),
    }

    try:
        result = await langfuse.async_api.metrics.get(query=query) # type: ignore
    except Exception as exc:
        raise RuntimeError(f"Langfuse metrics fetch failed: {exc}") from exc

    metrics: list[CostMetric] = []
    for row in result.data:
        model_name = row.get("providedModelName", "unknown")
        total_tokens = int(row.get("sum_totalTokens", 0))
        actual_cost = float(row.get("sum_totalCost", 0.0))

        if actual_cost <= _ZERO_COST_EPSILON and total_tokens > 0:
            in_tok, out_tok = _split_tokens(total_tokens)
            shadow_cost = _price(
                in_tok, out_tok,
                settings.gemini_flash_input_per_1m,
                settings.gemini_flash_output_per_1m,
            )
            metrics.append(
                CostMetric(
                    model_name=model_name,
                    total_cost_usd=shadow_cost,
                    total_tokens=total_tokens,
                    request_count=int(row.get("count_count", 0)),
                    is_shadow_cost=True,
                )
            )
        else:
            metrics.append(
                CostMetric(
                    model_name=model_name,
                    total_cost_usd=actual_cost,
                    total_tokens=total_tokens,
                    request_count=int(row.get("count_count", 0)),
                    is_shadow_cost=False,
                )
            )
    return metrics


async def build_cost_comparison(from_ts: datetime, to_ts: datetime) -> CostComparison:
    metrics = await fetch_cost_metrics(from_ts, to_ts)
    total_tokens = sum(m.total_tokens for m in metrics)
    query_count = sum(m.request_count for m in metrics)
    gemini_cost = sum(m.total_cost_usd for m in metrics)
    is_shadow = any(m.is_shadow_cost for m in metrics)

    in_tok, out_tok = _split_tokens(total_tokens)
    gpt4_cost = _price(in_tok, out_tok, settings.gpt4o_input_per_1m, settings.gpt4o_output_per_1m)

    savings = gpt4_cost - gemini_cost
    savings_pct = (savings / gpt4_cost * 100) if gpt4_cost > 0 else 0.0

    return CostComparison(
        period_start=from_ts,
        period_end=to_ts,
        total_tokens=total_tokens,
        query_count=query_count,
        gemini_cost_usd=gemini_cost,
        gemini_is_shadow_cost=is_shadow,
        gpt4_equivalent_cost_usd=gpt4_cost,
        savings_usd=savings,
        savings_pct=savings_pct,
    )


async def fetch_recent_audit_entries(limit: int = 50) -> list[AuditLogEntry]:
    langfuse = get_client()
    try:
        observations = await langfuse.async_api.observations.get_many(
            type="GENERATION", limit=limit, fields="core,basic,usage"
        )
    except Exception as exc:
        raise RuntimeError(f"Langfuse observations fetch failed: {exc}") from exc

    entries: list[AuditLogEntry] = []
    for obs in observations.data:
        decision = RoutingDecision(
            request_id=obs.id,
            timestamp=obs.start_time or datetime.now(timezone.utc),
            model_selected=obs.model or "unknown", # type: ignore
            routing_reason=(obs.metadata or {}).get("routing_reason", "n/a"),
            cost_usd=float(calculated_cost or 0.0), # type: ignore
            latency_ms=obs.latency or 0.0,
        )
        entries.append(
            AuditLogEntry(
                request_id=obs.id,
                timestamp=decision.timestamp,
                routing_decision=decision,
                masked_prompt_snippet=_mask_pii(str(obs.input or "")),
            )
        )
    return entries