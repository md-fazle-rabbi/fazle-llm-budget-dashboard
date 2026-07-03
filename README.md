# 💸 fazle-llm-budget-dashboard

Real-time LLM cost & routing intelligence dashboard. Reads historical cost/usage
data from Langfuse and real-time counters from Redis to answer one question for
AI teams: **"is our smart router actually saving money, and can we prove it?"**

Built as the companion to `fazle-llm-cost-router` (the FastAPI
router that makes the actual Gemini/GPT-4o routing decisions).

## Features

- 💵 Cost per 1,000 queries — your router vs. GPT-4-only baseline
- 📉 Tokens saved via caching (real-time, Redis-backed)
- 🥧 Model distribution (which model handled how many requests)
- 📈 Projected monthly savings at 10K / 100K / 1M query volume
- 🔐 Audit trail: request → routing decision → log entry, with PII-masked
  prompt snippets (OWASP LLM02:2025)
- ⚠️ Automatically flags free-tier ("shadow cost") numbers as estimates,
  never presents them as real bills

## Architecture

Two data sources, two purposes:

| Source   | Purpose                                  | Latency        |
|----------|-------------------------------------------|----------------|
| Langfuse | Historical cost/token aggregates          | Query-time     |
| Redis    | Real-time counters (cache hits, timeline) | Sub-millisecond|

This dashboard is **read-only** with respect to LLM providers — it never
calls Gemini or GPT-4o itself. All model calls happen in the Day 2 router;
this app only visualizes what was already logged.

## Tech stack

Python 3.14 · Streamlit · Plotly · Redis (Lua scripts for atomic aggregation)
· Langfuse Metrics API v2 · Pydantic v2 · uv

## Project structure

\```
app/
├── main.py              # Streamlit entrypoint
├── config.py             # Pydantic settings, loaded from .env
├── schemas.py             # Pydantic models
├── langfuse_client.py      # Langfuse Metrics + Observations API wrapper
├── redis_aggregator.py      # Lua-script-based atomic real-time counters
├── charts.py                # Plotly figure builders
├── audit_panel.py             # Audit-trail UI
└── lua/                        # record_event.lua, get_timeline.lua
scripts/
└── seed_demo_data.py    # Populate Redis with fake events for local testing
\```

## Prerequisites

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- Docker (for local Redis, or full container test)
- A Langfuse project with at least one logged generation (from the Day 2 router)

## Setup

\```bash
uv sync

docker run -d --name dev-redis -p 6379:6379 redis:7-alpine

cp .env.example .env

uv run python scripts/seed_demo_data.py   # optional: fake data for testing

uv run streamlit run app/main.py
\```

## Environment variables

| Variable                        | Required | Description                                      |
|----------------------------------|----------|---------------------------------------------------|
| `LANGFUSE_PUBLIC_KEY`             | Yes      | Langfuse project public key                        |
| `LANGFUSE_SECRET_KEY`              | Yes      | Langfuse project secret key — never hardcode        |
| `LANGFUSE_BASE_URL`                 | No       | Default `https://cloud.langfuse.com`                 |
| `LANGFUSE_PROJECT_ID`                | No       | Enables "View in Langfuse" deep link in sidebar        |
| `REDIS_URL`                            | Yes      | `redis://` or `rediss://` connection string              |
| `CACHE_TTL_SECONDS`                     | No       | Default `30`                                                |
| `REDIS_TIMELINE_WINDOW_SECONDS`          | No       | Default `604800` (7 days)                                     |

No Gemini/OpenAI API keys are needed here — see [Architecture](#architecture).

## Docker

\```bash
docker build -t fazle-llm-budget-dashboard .
docker run -p 8501:8501 --env-file .env fazle-llm-budget-dashboard
\```

If Redis is running on the host (not in the same Docker network), use
`REDIS_URL=redis://host.docker.internal:6379/0` on Windows/Mac Docker Desktop,
or `--network host` on Linux.

## Deployment (Render)

`render.yaml` provisions a Docker web service plus a managed key-value
(Redis-compatible) store. Push to `main`, create a Blueprint on Render, set
the Langfuse secrets, deploy.

## Security notes

- Secrets loaded via `pydantic-settings` from `.env` — never hardcoded
  (OWASP LLM02:2025)
- All displayed prompt snippets are PII-masked (email/phone regex redaction)
  before rendering
- Shadow-cost (free-tier) figures are always visually flagged as estimates

## Related

- `fazle-llm-cost-router` — the FastAPI router that makes the actual
  routing decisions this dashboard visualizes

---

**Author:** 
**Fazle Rabbi** — AI Engineer