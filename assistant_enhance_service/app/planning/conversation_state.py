from __future__ import annotations
import copy
from dataclasses import asdict, dataclass, field
from typing import Any
from app.entity.canonical import normalize_entity_scope
from app.planning.plan import AnalyticalPlan
MAX_HISTORY = 1
STATE_FIELDS = ('intent', 'user_objective', 'metric', 'dimensions', 'filters', 'group_by', 'time_range', 'sort', 'limit', 'retrieval_scope', 'query_mode', 'compare_to', 'entity_scope')

def plan_snapshot(plan: AnalyticalPlan | dict[str, Any] | None) -> dict[str, Any]:
    if plan is None:
        return {}
    data = plan.to_dict() if isinstance(plan, AnalyticalPlan) else dict(plan)
    snap = {k: copy.deepcopy(data.get(k)) for k in STATE_FIELDS if k in data}
    if snap.get('entity_scope'):
        snap['entity_scope'] = normalize_entity_scope(snap['entity_scope'])
    return snap

@dataclass
class ConversationStateModel:
    current_state: dict[str, Any] = field(default_factory=dict)
    previous_state: dict[str, Any] | None = None
    state_history: list[dict[str, Any]] = field(default_factory=list)
    short_context_summary: str = ''

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ConversationStateModel:
        if not data:
            return cls()
        return cls(current_state=dict(data.get('current_state') or {}), previous_state=dict(data['previous_state']) if data.get('previous_state') else None, state_history=list(data.get('state_history') or []), short_context_summary=str(data.get('short_context_summary') or ''))

    def advance(self, snapshot: dict[str, Any]) -> None:
        if not snapshot:
            return
        if self.current_state:
            self.previous_state = copy.deepcopy(self.current_state)
            self.state_history.append(copy.deepcopy(self.current_state))
            if len(self.state_history) > MAX_HISTORY:
                self.state_history = self.state_history[-MAX_HISTORY:]
        self.current_state = copy.deepcopy(snapshot)
        from app.planning.state_summary import short_context_summary
        self.short_context_summary = short_context_summary(snapshot)

def load_conversation_state(mem: dict[str, Any] | None) -> ConversationStateModel:
    if not mem:
        return ConversationStateModel()
    raw = mem.get('conversation_state')
    if not raw:
        raw = (mem.get('plan') or {}).get('conversation_state')
    if raw:
        return ConversationStateModel.from_dict(raw)
    plan = mem.get('plan') or {}
    ap = plan.get('analytical_plan') or plan
    if ap:
        snap = plan_snapshot(ap)
        if snap:
            return ConversationStateModel(current_state=snap)
    return ConversationStateModel()

def load_previous_plan(mem_plan: dict[str, Any] | None) -> AnalyticalPlan | None:
    if not mem_plan:
        return None
    if 'current_state' in mem_plan and mem_plan.get('current_state'):
        return AnalyticalPlan.from_dict(mem_plan['current_state'])
    if 'analytical_plan' in mem_plan:
        return AnalyticalPlan.from_dict(_strip_nested_scope(mem_plan['analytical_plan']))
    raw = mem_plan.get('conversation_state') or mem_plan
    if isinstance(raw, dict) and raw.get('current_state'):
        return AnalyticalPlan.from_dict(raw['current_state'])
    return AnalyticalPlan.from_dict(_strip_nested_scope(raw))

def _strip_nested_scope(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}
    out = dict(data)
    out.pop('conversation_scope', None)
    return out

def persist_turn_state(mem: dict[str, Any], plan: AnalyticalPlan, *, objective_resolution: dict[str, Any] | None=None, dimension_resolution: dict[str, Any] | None=None, temporal_resolution: dict[str, Any] | None=None, semantic_resolution: dict[str, Any] | None=None, business_semantic_resolution: dict[str, Any] | None=None) -> dict[str, Any]:
    conv = load_conversation_state(mem)
    snap = plan_snapshot(plan)
    conv.advance(snap)
    mem['conversation_state'] = conv.to_dict()
    envelope = {'analytical_plan': snap, 'conversation_state': conv.to_dict(), 'intent': plan.intent, 'user_objective': plan.user_objective, 'metric': plan.metric, 'dimensions': plan.dimensions, 'filters': plan.filters, 'group_by': plan.group_by, 'time_range': plan.time_range, 'sort': plan.sort, 'limit': plan.limit, 'query_mode': plan.query_mode, 'compare_to': plan.compare_to, 'entities': mem.get('entities', {})}
    if objective_resolution:
        envelope['objective_resolution'] = objective_resolution
    if dimension_resolution:
        envelope['dimension_resolution'] = dimension_resolution
    if temporal_resolution:
        envelope['temporal_resolution'] = temporal_resolution
    if semantic_resolution:
        envelope['semantic_resolution'] = semantic_resolution
    if business_semantic_resolution:
        envelope['business_semantic_resolution'] = business_semantic_resolution
    mem['plan'] = envelope
    return envelope