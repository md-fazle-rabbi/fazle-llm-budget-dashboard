from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import streamlit as st
from pydantic import ValidationError

from app.audit_panel import render_audit_panel
from app.charts import (
    cost_per_1k_queries_chart,
    model_distribution_pie,
    monthly_projection_chart,
    routing_history_table,
    tokens_saved_chart,
)
from app.config import settings
from app.langfuse_client import build_cost_comparison, fetch_recent_audit_entries
from app.redis_aggregator import aggregator
from app.schemas import RoutingDecision

st.set_page_config(page_title="LLM Budget & Routing Dashboard", page_icon="💸", layout="wide")


@st.cache_resource
def get_event_loop() -> asyncio.AbstractEventLoop:
    return asyncio.new_event_loop()


def run_async(coro):
    return get_event_loop().run_until_complete(coro)


st.title("💸 LLM Cost & Routing Intelligence Dashboard")
st.caption(
    "Live routing data from Langfuse + real-time aggregation via Redis. "
    "Built for AI teams who need to prove — not guess — their LLM spend."
)

with st.sidebar:
    st.header("⚙️ Settings")
    window_hours = st.selectbox(
        "Time window", [1, 6, 24, 168], index=2, format_func=lambda h: f"Last {h}h"
    )
    auto_refresh = st.checkbox("Auto-refresh every 30s", value=False)
    st.divider()
    st.caption("Sources: Langfuse Metrics API v2 (historical) + Redis (real-time counters).")

    if settings.langfuse_project_id:
        st.link_button(
            "🔗 View raw traces in Langfuse",
            f"{settings.langfuse_base_url}/project/{settings.langfuse_project_id}/traces",
            width="stretch",
        )

if auto_refresh:
    st.markdown('<meta http-equiv="refresh" content="30">', unsafe_allow_html=True)

to_ts = datetime.now(timezone.utc)
from_ts = to_ts - timedelta(hours=window_hours)

with st.spinner("Fetching cost data from Langfuse..."):
    try:
        comparison = run_async(build_cost_comparison(from_ts, to_ts))
    except ValidationError as exc:
        st.error(
            "❌ **Pydantic ValidationError while building the cost comparison.** "
            "Langfuse's response shape didn't match what `app/schemas.py` expects. "
            "Check `uv pip show langfuse` — a Langfuse SDK upgrade/downgrade is the "
            "most common cause of this."
        )
        st.exception(exc)
        st.stop()
    except RuntimeError as exc:
        st.error(f"Langfuse fetch failed: {exc}")
        st.caption(
            "If this mentions an attribute error, your installed `langfuse` SDK version "
            "may use different method names than expected. Run `uv pip show langfuse` "
            "to check the version."
        )
        st.stop()

if comparison.gemini_is_shadow_cost:
    st.warning(
        "⚠️ **Estimated (free tier) — not an actual bill.** Gemini 2.5 Flash usage is "
        "on the free tier, so Langfuse's actual billed cost is $0. Numbers below are "
        "computed from token counts × published paid-tier pricing — clearly flagged."
    )

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Queries", f"{comparison.query_count:,}")
col2.metric("Total Tokens", f"{comparison.total_tokens:,}")
col3.metric(
    "Your Cost" + (" (est.)" if comparison.gemini_is_shadow_cost else ""),
    f"${comparison.gemini_cost_usd:.4f}",
)
col4.metric("Savings vs GPT-4", f"{comparison.savings_pct:.1f}%", delta=f"${comparison.savings_usd:.4f}")

st.divider()

with st.spinner("Reading real-time Redis aggregates..."):
    try:
        model_aggregates = run_async(aggregator.get_model_aggregates())
        cache_stats = run_async(aggregator.get_cache_stats())
    except Exception as exc:
        st.error(f"Redis aggregator failed: {exc}")
        model_aggregates, cache_stats = {}, {}

c1, c2 = st.columns(2)
with c1:
    st.plotly_chart(cost_per_1k_queries_chart(comparison), width="stretch", theme=None)
with c2:
    st.plotly_chart(tokens_saved_chart(cache_stats), width="stretch", theme=None)

c3, c4 = st.columns(2)
with c3:
    st.plotly_chart(model_distribution_pie(model_aggregates), width="stretch", theme=None)
with c4:
    st.plotly_chart(monthly_projection_chart(comparison), width="stretch", theme=None)

st.divider()
st.subheader("📜 Routing Decision History")
with st.spinner("Loading recent routing events..."):
    try:
        recent_events = run_async(aggregator.get_recent_events(window_seconds=window_hours * 3600))
    except Exception as exc:
        st.error(f"Could not load routing history: {exc}")
        recent_events = []

if recent_events:
    decisions = [
        RoutingDecision(
            request_id=e["request_id"],
            timestamp=datetime.fromtimestamp(e["timestamp"], tz=timezone.utc),
            model_selected=e["model"],
            routing_reason=e.get("routing_reason", "n/a"),
            cost_usd=e["cost"],
            latency_ms=e.get("latency_ms", 0.0),
            tokens_used=e.get("tokens", 0),
            cache_hit=e.get("cache_hit", False),
        )
        for e in recent_events
    ]
    st.plotly_chart(routing_history_table(decisions), width="stretch", theme=None)
else:
    st.info("No routing events recorded in this window yet. Run scripts/seed_demo_data.py to test.")

st.divider()

with st.spinner("Loading audit trail from Langfuse..."):
    try:
        audit_entries = run_async(fetch_recent_audit_entries(limit=50))
    except RuntimeError as exc:
        st.error(f"Audit trail fetch failed: {exc}")
        audit_entries = []

render_audit_panel(audit_entries)

st.divider()
st.caption(
    "🔗 MCP-compatible: build_cost_comparison() and get_model_aggregates() can be "
    "exposed as MCP tools. Observability: Langfuse. Security: OWASP LLM02:2025 "
    "PII masking on all display layers."
)