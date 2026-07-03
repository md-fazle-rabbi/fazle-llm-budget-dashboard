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

_DARK = {
    "bg": "#0E1117",
    "card": "#1C1E26",
    "card_alt": "#22242E",
    "text": "#FAFAFA",
    "grid": "#2A2C38",
}


def _apply_dark_layout(fig: go.Figure, title: str, **extra) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, font=dict(color=_DARK["text"])),
        paper_bgcolor=_DARK["bg"],
        plot_bgcolor=_DARK["bg"],
        font=dict(color=_DARK["text"]),
        margin=dict(t=60, b=40, l=40, r=30, pad=4),
        **extra,
    )
    return fig


def tokens_saved_chart(cache_stats: dict[str, int]) -> go.Figure:
    """Tokens Saved vs Baseline"""
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
                textfont=dict(color=_DARK["text"]),
            )
        ]
    )
    return _apply_dark_layout(
        fig,
        title=f"Tokens Saved via Caching: {tokens_saved:,} tokens",
        yaxis=dict(title="Total Tokens", color=_DARK["text"], gridcolor=_DARK["grid"], automargin=True),
        xaxis=dict(color=_DARK["text"], automargin=True),
        showlegend=False,
    )


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
                textfont=dict(color=_DARK["text"]),
            )
        ]
    )
    return _apply_dark_layout(
        fig,
        title=f"Cost per 1,000 Queries — {comparison.savings_pct:.1f}% savings",
        yaxis=dict(
            title="USD per 1,000 queries", color=_DARK["text"], gridcolor=_DARK["grid"], automargin=True
        ),
        xaxis=dict(color=_DARK["text"], automargin=True),
        showlegend=False,
    )


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
                textfont=dict(color=_DARK["text"]),
            )
        ]
    )
    return _apply_dark_layout(
        fig,
        title="Model Distribution (by request count)",
        legend=dict(font=dict(color=_DARK["text"])),
    )


def routing_history_table(decisions: list[RoutingDecision]) -> go.Figure:
    recent = sorted(decisions, key=lambda d: d.timestamp, reverse=True)[:25]
    row_colors = [_DARK["card"] if i % 2 == 0 else _DARK["card_alt"] for i in range(len(recent))]

    fig = go.Figure(
        data=[
            go.Table(
                header=dict(
                    values=["Timestamp", "Model", "Reason", "Cost ($)", "Latency (ms)", "Cache?"],
                    fill_color=_C["primary"],
                    font=dict(color="white", size=13),
                    align="left",
                    height=32,
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
                    fill_color=[row_colors] * 6,
                    font=dict(color=_DARK["text"], size=12),
                    align="left",
                    height=28,
                ),
            )
        ]
    )
    return _apply_dark_layout(fig, title="Recent Routing Decisions")


def monthly_projection_chart(comparison: CostComparison) -> go.Figure:
    """10K/100K/1M query volume-এ projected monthly savings — sales closer।"""
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
    return _apply_dark_layout(
        fig,
        title="Projected Monthly Cost by Query Volume",
        xaxis=dict(title="Monthly Queries", color=_DARK["text"], automargin=True),
        yaxis=dict(
            title="Projected USD / month", color=_DARK["text"], gridcolor=_DARK["grid"], automargin=True
        ),
        barmode="group",
        legend=dict(font=dict(color=_DARK["text"])),
    )