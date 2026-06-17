from __future__ import annotations
import json
from typing import Any
import redis
from app.config import settings
from app.planning.state_summary import conversation_context_text

class RedisMemory:

    def __init__(self, namespace: str | None=None) -> None:
        self.client = redis.from_url(settings.redis_url, decode_responses=True)
        self.max_turns = settings.redis_max_turns
        self.ttl = settings.redis_memory_ttl
        self.namespace = (namespace or settings.analytics_redis_namespace).rstrip(':')

    def memory_key(self, session_id: str) -> str:
        return f'{self.namespace}:{session_id}'

    def _key(self, session_id: str) -> str:
        return self.memory_key(session_id)

    def exists(self, session_id: str) -> bool:
        return bool(self.client.exists(self._key(session_id)))

    def load(self, session_id: str) -> dict[str, Any]:
        raw = self.client.get(self._key(session_id))
        if not raw:
            return {'exchanges': [], 'entities': {}, 'filters': {}, 'time_range': {}, 'plan': {}, 'context': {}}
        return json.loads(raw)

    def save(self, session_id: str, state: dict[str, Any]) -> None:
        self.client.setex(self._key(session_id), self.ttl, json.dumps(state, default=str))

    def add_exchange(self, session_id: str, role: str, content: str) -> None:
        mem = self.load(session_id)
        mem.setdefault('exchanges', []).append({'role': role, 'content': content})
        if len(mem['exchanges']) > self.max_turns * 2:
            mem['exchanges'] = mem['exchanges'][-(self.max_turns * 2):]
        self.save(session_id, mem)

    def update_context(self, session_id: str, entities: dict, filters: dict, time_range: dict, plan: dict, context: dict) -> None:
        mem = self.load(session_id)
        mem['entities'] = entities
        mem['filters'] = filters
        if time_range:
            mem['time_range'] = time_range
        mem['plan'] = plan
        mem['context'] = context
        if isinstance(plan, dict) and plan.get('conversation_state'):
            mem['conversation_state'] = plan['conversation_state']
        self.save(session_id, mem)

    def context_size(self, session_id: str) -> int:
        mem = self.load(session_id)
        return len(mem.get('exchanges', []))

    def loaded_context(self, session_id: str) -> dict[str, Any]:
        mem = self.load(session_id)
        return {'exchanges': mem.get('exchanges', []), 'entities': mem.get('entities', {}), 'filters': mem.get('filters', {}), 'time_range': mem.get('time_range', {}), 'plan': mem.get('plan', {}), 'analysis_context': mem.get('context', {})}

    def context_text(self, session_id: str) -> str:
        mem = self.load(session_id)
        return conversation_context_text(mem, max_exchanges=2)