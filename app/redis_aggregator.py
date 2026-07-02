import json
import time
from pathlib import Path
from typing import Any

import redis.asyncio as redis

from app.config import settings
from app.schemas import RoutingDecision

_TIMELINE_KEY = "agg:timeline"
_MODEL_HASH_PREFIX = "agg:model:"
_CACHE_HASH_KEY = "agg:cache"
_KNOWN_MODELS_SET = "agg:known_models"

_LUA_DIR = Path(__file__).resolve().parent / "lua"


def _load_lua(filename: str) -> str:
    return (_LUA_DIR / filename).read_text(encoding="utf-8")


class RedisAggregator:
    """Redis connection + registered Lua script — singleton-style client।"""

    def __init__(self) -> None:
        self._client: "redis.Redis | None" = None
        self._record_script = None
        self._timeline_script = None

    async def connect(self) -> None:
        if self._client is not None:
            return
        self._client = redis.from_url(settings.redis_url, decode_responses=True)
        self._record_script = self._client.register_script(_load_lua("record_event.lua"))
        self._timeline_script = self._client.register_script(_load_lua("get_timeline.lua"))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def record_event(self, decision: RoutingDecision) -> None:
        if self._client is None:
            await self.connect()
        assert self._client is not None
        assert self._record_script is not None

        event_payload = json.dumps(
            {
                "request_id": decision.request_id,
                "model": decision.model_selected,
                "routing_reason": decision.routing_reason,
                "cost": decision.cost_usd,
                "latency_ms": decision.latency_ms,
                "tokens": decision.tokens_used,
                "cache_hit": decision.cache_hit,
                "timestamp": decision.timestamp.timestamp(),
            }
        )
        model_hash_key = f"{_MODEL_HASH_PREFIX}{decision.model_selected}"

        await self._record_script(
            keys=[_TIMELINE_KEY, model_hash_key, _CACHE_HASH_KEY, _KNOWN_MODELS_SET],
            args=[
                event_payload,
                decision.timestamp.timestamp(),
                decision.model_selected,
                decision.cost_usd,
                decision.tokens_used,
                settings.redis_timeline_window_seconds,
                "1" if decision.cache_hit else "0",
            ],
        )

    async def get_model_aggregates(self) -> dict[str, dict[str, Any]]:
        if self._client is None:
            await self.connect()
        assert self._client is not None

        model_names = await self._client.smembers(_KNOWN_MODELS_SET)
        result: dict[str, dict[str, Any]] = {}
        for model_name_raw in model_names:
            model_name = model_name_raw if isinstance(model_name_raw, str) else bytes(model_name_raw).decode("utf-8")
            data = await self._client.hgetall(f"{_MODEL_HASH_PREFIX}{model_name}")
            result[model_name] = {
                "cost": float(data.get("cost", 0.0)),
                "tokens": int(float(data.get("tokens", 0))),
                "count": int(data.get("count", 0)),
            }
        return result

    async def get_cache_stats(self) -> dict[str, int]:
        if self._client is None:
            await self.connect()
        assert self._client is not None

        data = await self._client.hgetall(_CACHE_HASH_KEY)
        return {
            "hits": int(data.get("hits", 0)),
            "misses": int(data.get("misses", 0)),
            "tokens_saved": int(data.get("tokens_saved", 0)),
            "tokens_processed": int(data.get("tokens_processed", 0)),
        }

    async def get_recent_events(self, window_seconds: int = 86400) -> list[dict[str, Any]]:
        if self._client is None:
            await self.connect()
        assert self._client is not None
        assert self._timeline_script is not None

        now = time.time()
        raw = await self._timeline_script(keys=[_TIMELINE_KEY], args=[now, window_seconds])
        return [json.loads(item) for item in raw]


aggregator = RedisAggregator()