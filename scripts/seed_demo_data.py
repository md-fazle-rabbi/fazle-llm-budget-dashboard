import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone

from app.redis_aggregator import aggregator
from app.schemas import RoutingDecision

_MODELS = ["gemini-2.5-flash", "gpt-4o", "claude-sonnet-5"]
_REASONS = ["low complexity → cheap model", "high complexity → premium model", "cache hit"]


async def seed(n: int = 200) -> None:
    now = datetime.now(timezone.utc)
    for _ in range(n):
        cache_hit = random.random() < 0.3
        decision = RoutingDecision(
            request_id=str(uuid.uuid4()),
            timestamp=now - timedelta(minutes=random.randint(0, 1440)),
            model_selected=random.choice(_MODELS),
            routing_reason=random.choice(_REASONS),
            cost_usd=0.0 if cache_hit else round(random.uniform(0.0001, 0.01), 6),
            latency_ms=round(random.uniform(200, 1800), 1),
            tokens_used=random.randint(150, 2200),
            cache_hit=cache_hit,
        )
        await aggregator.record_event(decision)
    print(f"✅ {n} demo routing events were seeded into Redis.")


if __name__ == "__main__":
    asyncio.run(seed())