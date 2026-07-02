"""Audit-trail panel — request → routing decision → log entry chain।"""

from __future__ import annotations

import streamlit as st

from app.schemas import AuditLogEntry


def render_audit_panel(entries: list[AuditLogEntry]) -> None:
    st.subheader("🔐 Audit Trail — Request → Routing Decision → Log Entry")
    st.caption(
        "Every prompt snippet below is PII-masked before display (OWASP LLM02:2025). "
        "Satisfies the MCP 2026-07-28 audit-logging expectation for enterprise buyers."
    )

    if not entries:
        st.info("No recent audit entries found in this time window.")
        return

    for entry in entries[:20]:
        decision = entry.routing_decision
        with st.expander(
            f"🧾 {entry.request_id[:12]}...  ·  {decision.model_selected}  ·  "
            f"{entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
        ):
            col1, col2, col3 = st.columns(3)
            col1.metric("Model", decision.model_selected)
            col2.metric("Cost (USD)", f"${decision.cost_usd:.5f}")
            col3.metric("Latency", f"{decision.latency_ms:.0f} ms")

            st.markdown("**Chain:**")
            st.code(
                f"1. Request received   → request_id={entry.request_id}\n"
                f"2. Routing decision   → model={decision.model_selected}, "
                f'reason="{decision.routing_reason}"\n'
                f"3. Log entry recorded → timestamp={entry.timestamp.isoformat()}",
                language="text",
            )

            st.markdown("**Masked Prompt Snippet (PII-redacted):**")
            st.text(entry.masked_prompt_snippet or "(empty)")