from __future__ import annotations
from typing import Any
from app.planning.plan import AnalyticalPlan
_SUMMARY_KEYS = ('metric', 'user_objective', 'filters', 'time_range', 'retrieval_scope', 'entity_scope', 'query_mode')

def compact_snapshot(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data:
        return {}
    return {k: data[k] for k in _SUMMARY_KEYS if data.get(k) not in (None, {}, [])}

def short_context_summary(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return ''
    parts: list[str] = []
    if snapshot.get('metric'):
        parts.append(str(snapshot['metric']))
    if snapshot.get('user_objective'):
        parts.append(str(snapshot['user_objective']))
    filters = snapshot.get('filters') or {}
    if filters:
        parts.append('filters=' + ','.join((f'{k}:{v}' for (k, v) in filters.items())))
    tr = snapshot.get('time_range') or {}
    if tr.get('preset'):
        parts.append(str(tr['preset']))
    scope = snapshot.get('entity_scope') or {}
    if scope.get('location'):
        parts.append(f"at {scope['location']}")
    elif scope.get('plate_suffix'):
        parts.append(f"plate_suffix={scope['plate_suffix']}")
    return ' | '.join(parts)

def active_state_for_resolver(previous: AnalyticalPlan | None, *, prior_concept: str | None, inherit: bool) -> dict[str, Any]:
    if not previous:
        return {'inherit_scope': False}
    return {'active_metric': previous.metric, 'active_objective': previous.user_objective, 'active_filters': previous.filters, 'active_time_range': previous.time_range, 'active_retrieval_scope': previous.retrieval_scope, 'active_entity_scope': previous.entity_scope, 'prior_business_concept': prior_concept, 'inherit_scope': inherit}

def conversation_context_text(mem: dict[str, Any], *, max_exchanges: int=2) -> str:
    from app.planning.conversation_state import load_conversation_state
    conv = load_conversation_state(mem)
    lines: list[str] = []
    current = compact_snapshot(conv.current_state)
    if current:
        lines.append(f'Current state: {short_context_summary(current)}')
    previous = compact_snapshot(conv.previous_state)
    if previous:
        lines.append(f'Previous state: {short_context_summary(previous)}')
    entities = mem.get('entities') or current.get('entity_scope') or {}
    if entities:
        lines.append(f'Active entities: {entities}')
    filters = mem.get('filters') or current.get('filters') or {}
    if filters:
        lines.append(f'Active filters: {filters}')
    metric = current.get('metric') or (mem.get('plan') or {}).get('metric')
    if metric:
        lines.append(f'Active metric: {metric}')
    for ex in mem.get('exchanges', [])[-max_exchanges:]:
        role = ex.get('role', 'user').upper()
        content = str(ex.get('content', ''))[:200]
        lines.append(f'{role}: {content}')
    return '\n'.join(lines)

def summarize_turn(plan: AnalyticalPlan) -> str:
    from app.planning.conversation_state import plan_snapshot
    return short_context_summary(plan_snapshot(plan))