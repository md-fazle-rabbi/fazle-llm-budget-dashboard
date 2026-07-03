import asyncio
import base64
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError

from app.config import settings
from app.schemas import AuditLogEntry, CostComparison, CostMetric, RoutingDecision

logger = logging.getLogger(__name__)

_PII_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"\b\d{10,}\b"),
]

_ZERO_COST_EPSILON = 1e-9
_REQUEST_TIMEOUT_S = 30


def build_project_trace_url() -> str | None:
    if not settings.langfuse_project_id:
        return None
    return f"{settings.langfuse_base_url}/project/{settings.langfuse_project_id}/traces"


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


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    """Read a field off a result row whether it comes back as a dict or an object."""
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _row_get_any(row: Any, *keys: str, default: Any = None) -> Any:
    """Try several possible key spellings (snake_case vs camelCase) in order."""
    for key in keys:
        value = _row_get(row, key, None)
        if value is not None:
            return value
    return default


def _safe_model_name(raw: Any) -> str:
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return "unknown_model"


# --- Direct REST calls to the Langfuse Public API ---------------------------
# We call GET /api/public/v2/metrics and GET /api/public/v2/observations
# directly instead of going through the langfuse-python SDK's resource
# wrappers. Those wrappers have moved (langfuse.metrics -> langfuse.api.metrics
# -> internal renames within .api itself between point releases) more than
# once, and every rename breaks this integration again. The REST contract
# below is Langfuse's stable, documented public interface:
# https://langfuse.com/docs/metrics/features/metrics-api
# https://langfuse.com/docs/api-and-data-platform/features/observations-api
# Using stdlib urllib only, so this doesn't add a new dependency.

def _basic_auth_header() -> str:
    token = f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode("utf-8")
    return "Basic " + base64.b64encode(token).decode("ascii")


def _rest_get(path: str, params: dict[str, Any]) -> dict:
    clean_params = {k: v for k, v in params.items() if v is not None}
    query_string = urllib.parse.urlencode(clean_params)
    url = f"{settings.langfuse_base_url.rstrip('/')}{path}?{query_string}"

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": _basic_auth_header(),
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_REQUEST_TIMEOUT_S) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(
            f"Langfuse API returned HTTP {exc.code} for {path}: {detail or exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach Langfuse at {settings.langfuse_base_url}: {exc.reason}") from exc

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Langfuse API returned non-JSON response for {path}") from exc


def _fetch_metrics_raw(query: dict) -> dict:
    return _rest_get("/api/public/v2/metrics", {"query": json.dumps(query)})


def _fetch_observations_raw(*, type: str | None = None, limit: int | None = None, fields: str | None = None) -> dict:
    return _rest_get(
        "/api/public/v2/observations",
        {"type": type, "limit": limit, "fields": fields},
    )


async def fetch_cost_metrics(from_ts: datetime, to_ts: datetime) -> list[CostMetric]:
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
        result = await asyncio.to_thread(_fetch_metrics_raw, query)
    except Exception as exc:
        raise RuntimeError(f"Langfuse metrics fetch failed: {exc}") from exc

    rows = result.get("data") or []

    metrics: list[CostMetric] = []
    for row in rows:
        try:
            model_name = _safe_model_name(_row_get(row, "providedModelName"))
            total_tokens = int(_row_get(row, "sum_totalTokens") or 0)
            actual_cost = float(_row_get(row, "sum_totalCost") or 0.0)
            request_count = int(_row_get(row, "count_count") or 0)

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
                        request_count=request_count,
                        is_shadow_cost=True,
                    )
                )
            else:
                metrics.append(
                    CostMetric(
                        model_name=model_name,
                        total_cost_usd=actual_cost,
                        total_tokens=total_tokens,
                        request_count=request_count,
                        is_shadow_cost=False,
                    )
                )
        except (ValidationError, TypeError, ValueError) as exc:
            # One malformed telemetry row should never take down the whole dashboard.
            logger.warning("Skipping malformed Langfuse metrics row: %s (row=%r)", exc, row)
            continue

    return metrics


async def build_cost_comparison(from_ts: datetime, to_ts: datetime) -> CostComparison:
    """Gemini (actual/shadow) cost vs GPT-4o counterfactual cost — headline ROI number."""
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
    try:
        observations = await asyncio.to_thread(
            _fetch_observations_raw,
            type="GENERATION",
            limit=limit,
            fields="core,basic,usage",
        )
    except Exception as exc:
        raise RuntimeError(f"Langfuse observations fetch failed: {exc}") from exc

    rows = observations.get("data") or []

    entries: list[AuditLogEntry] = []
    for obs in rows:
        try:
            obs_id = _row_get_any(obs, "id", default="unknown")
            start_time_raw = _row_get_any(obs, "startTime", "start_time")
            start_time = _parse_timestamp(start_time_raw)
            model_name = _safe_model_name(
                _row_get_any(obs, "providedModelName", "provided_model_name")
            )
            metadata = _row_get(obs, "metadata")
            if not isinstance(metadata, dict):
                metadata = {}
            total_cost = _row_get_any(obs, "totalCost", "total_cost", default=0.0)
            latency = _row_get(obs, "latency") or 0.0
            raw_input = _row_get(obs, "input")

            decision = RoutingDecision(
                request_id=obs_id,
                timestamp=start_time or datetime.now(timezone.utc),
                model_selected=model_name,
                routing_reason=metadata.get("routing_reason", "n/a"),
                cost_usd=total_cost or 0.0,
                latency_ms=latency * 1000,
            )
            entries.append(
                AuditLogEntry(
                    request_id=obs_id,
                    timestamp=decision.timestamp,
                    routing_decision=decision,
                    masked_prompt_snippet=_mask_pii(str(raw_input or "")),
                )
            )
        except (ValidationError, TypeError, ValueError) as exc:
            logger.warning("Skipping malformed Langfuse observation row: %s", exc)
            continue

    return entries


def _parse_timestamp(value: Any) -> datetime | None:
    """REST responses give startTime as an ISO-8601 string, not a datetime object."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None