from __future__ import annotations

import plotly.graph_objects as go

from app.schemas import CostComparison, RoutingDecision

_C = {
    "primary": "#6C5CE7",
    "secondary": "#00B894",
    "warning": "#FDCB6E",
    "danger": "#D63031",
    "muted": "#B2BEC3",
}


def tokens_saved_chart(cache_stats: dict[str, int]) -> go.Figure:
    tokens_saved = cache_stats.get("tokens_saved", 0)
    tokens_processed = cache_stats.get("tokens_processed", 0)
    baseline = tokens_processed + tokens_saved

    fig = go.Figure(
        data=[
            go.Bar(
                x=["Baseline (No Cache)", "Actual (With Cache)"],
                y=[baseline, tokens_processed],
                marker_color=[_C["muted"], _C["secondary"]],
                text=[f"{baseline:,}", f"{tokens_processed:,}"],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title=f"Tokens Saved via Caching: {tokens_saved:,} tokens",
        yaxis_title="Total Tokens",
        template="plotly_white",
        showlegend=False,
    )
    return fig


def cost_per_1k_queries_chart(comparison: CostComparison) -> go.Figure:
    """'$/1K Queries (Yours vs GPT-4 Only)' — headline ROI bar chart।"""
    if comparison.query_count == 0:
        yours = gpt4 = 0.0
    else:
        yours = (comparison.gemini_cost_usd / comparison.query_count) * 1000
        gpt4 = (comparison.gpt4_equivalent_cost_usd / comparison.query_count) * 1000

    suffix = " (est.)" if comparison.gemini_is_shadow_cost else ""

    fig = go.Figure(
        data=[
            go.Bar(
                x=[f"Your Smart Router{suffix}", "GPT-4 Only (Baseline)"],
                y=[yours, gpt4],
                marker_color=[_C["primary"], _C["danger"]],
                text=[f"${yours:.2f}", f"${gpt4:.2f}"],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title=f"Cost per 1,000 Queries — {comparison.savings_pct:.1f}% savings",
        yaxis_title="USD per 1,000 queries",
        template="plotly_white",
        showlegend=False,
    )
    return fig


def model_distribution_pie(model_aggregates: dict[str, dict]) -> go.Figure:
    labels = list(model_aggregates.keys())
    values = [v.get("count", 0) for v in model_aggregates.values()]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.45,
                marker_colors=[_C["primary"], _C["secondary"], _C["warning"], _C["danger"]],
            )
        ]
    )
    fig.update_layout(title="Model Distribution (by request count)", template="plotly_white")
    return fig


def routing_history_table(decisions: list[RoutingDecision]) -> go.Figure:
    recent = sorted(decisions, key=lambda d: d.timestamp, reverse=True)[:25]

    fig = go.Figure(
        data=[
            go.Table(
                header=dict(
                    values=["Timestamp", "Model", "Reason", "Cost ($)", "Latency (ms)", "Cache?"],
                    fill_color=_C["primary"],
                    font=dict(color="white"),
                    align="left",
                ),
                cells=dict(
                    values=[
                        [d.timestamp.strftime("%Y-%m-%d %H:%M:%S") for d in recent],
                        [d.model_selected for d in recent],
                        [d.routing_reason for d in recent],
                        [f"{d.cost_usd:.5f}" for d in recent],
                        [f"{d.latency_ms:.0f}" for d in recent],
                        ["✅" if d.cache_hit else "—" for d in recent],
                    ],
                    align="left",
                ),
            )
        ]
    )
    fig.update_layout(title="Recent Routing Decisions", template="plotly_white")
    return fig


def monthly_projection_chart(comparison: CostComparison) -> go.Figure:
    if comparison.query_count == 0:
        per_query_yours = per_query_gpt4 = 0.0
    else:
        per_query_yours = comparison.gemini_cost_usd / comparison.query_count
        per_query_gpt4 = comparison.gpt4_equivalent_cost_usd / comparison.query_count

    volumes = [10_000, 100_000, 1_000_000]
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Your Smart Router",
            x=[f"{v:,}" for v in volumes],
            y=[v * per_query_yours for v in volumes],
            marker_color=_C["primary"],
        )
    )
    fig.add_trace(
        go.Bar(
            name="GPT-4 Only",
            x=[f"{v:,}" for v in volumes],
            y=[v * per_query_gpt4 for v in volumes],
            marker_color=_C["danger"],
        )
    )
    fig.update_layout(
        title="Projected Monthly Cost by Query Volume",
        xaxis_title="Monthly Queries",
        yaxis_title="Projected USD / month",
        barmode="group",
        template="plotly_white",
    )
    return fig