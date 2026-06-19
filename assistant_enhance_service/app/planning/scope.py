from __future__ import annotations
import copy
import re
from typing import Any
from app.entity.canonical import merge_entity_scope, normalize_entity_scope
from app.planning.conversation_state import load_previous_plan, plan_snapshot
from app.planning.plan import AnalyticalPlan
from app.planning.state_preservation import preserve_sticky_scope

def question_references_peak_hour(question: str) -> bool:
    q = question.lower()
    return bool(re.search('\\b(?:that|the)\\s+hour\\b|\\bduring\\s+(?:that|the)\\s+hour\\b|\\bat\\s+that\\s+hour\\b|\\bpeak\\s+hour\\b', q))

def should_inherit(question: str, context: str, previous: AnalyticalPlan) -> bool:
    q = question.lower()
    tokens = q.split()
    if not tokens:
        return False
    refs = ('these', 'those', 'them', 'that', 'this', 'same', 'previous', 'above', 'other', 'another', 'it', 'there', 'here', 'of those', 'of them', 'of these', 'what about', 'how about', 'about')
    pattern = r'\b(?:' + '|'.join(re.escape(r) for r in refs) + r')\b'
    if re.search(pattern, q):
        return True
    if len(tokens) <= 4:
        return True
    start_words = ('how', 'show', 'rank', 'give', 'what', 'list', 'count', 'which', 'who', 'where', 'when', 'why', 'can')
    if len(tokens) <= 7 and tokens[0] not in start_words:
        return True
    return False

def merge_scope(previous: AnalyticalPlan | None, proposed: AnalyticalPlan, *, inherit: bool, question: str='') -> tuple[AnalyticalPlan, dict[str, Any]]:
    (merged, audit) = preserve_sticky_scope(previous, proposed, question=question, inherit=inherit)
    if not inherit or previous is None:
        audit.setdefault('inherit', False)
        audit['changes'] = audit.get('resolved_changes', ['new_scope'])
        return (merged, audit)
    audit['inherit'] = True
    audit['changes'] = audit.get('resolved_changes', [])
    return (merged, audit)

def _merge_entity_scope(current: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    return merge_entity_scope(current, incoming)

def _apply_entity_scope_to_filters(plan: AnalyticalPlan) -> None:
    scope = plan.entity_scope
    if scope.get('camera_id'):
        plan.filters['location'] = scope['camera_id']
    if scope.get('violation_type'):
        plan.filters['violation_type'] = scope['violation_type']
    if scope.get('vehicle_type'):
        plan.filters['vehicle_type'] = scope['vehicle_type']
    if scope.get('vehicle_category'):
        plan.filters['vehicle_category'] = scope['vehicle_category']
    if scope.get('peak_hour') is not None:
        plan.filters['hour'] = scope['peak_hour']
    from app.planning.semantic_normalization import apply_semantic_normalization
    apply_semantic_normalization(plan)

def update_scope_from_result(plan: AnalyticalPlan, columns: list[str], rows: list[tuple], camera_names: dict[str, str]) -> AnalyticalPlan:
    if not rows:
        return plan
    updated = copy.deepcopy(plan)
    data = [dict(zip(columns, r)) for r in rows]
    scope = dict(updated.entity_scope)
    if updated.query_mode in ('top_n', 'ranking', 'grouped_analysis') and data:
        row = data[0]
        cid = row.get('camera_id')
        if cid:
            scope['camera_id'] = str(cid)
            display = camera_names.get(str(cid), str(cid))
            scope = normalize_entity_scope({**scope, 'camera_id': str(cid), 'location': display, 'display': display}, camera_names=camera_names)
            updated.filters['location'] = str(cid)
        dims = updated.dimensions or updated.group_by or []
        if 'hour' in dims:
            period = row.get('period')
            if period is not None:
                try:
                    scope['peak_hour'] = int(period)
                    updated.filters['hour'] = int(period)
                except (TypeError, ValueError):
                    pass
    if updated.query_mode in ('count', 'aggregation') and len(data) == 1 and (len(columns) == 1):
        val = data[0].get(columns[0])
        if isinstance(val, (int, float)):
            scope['last_result_count'] = int(val)
    updated.entity_scope = normalize_entity_scope(scope, camera_names=camera_names)
    return updated

def entity_scope_from_resolutions(resolutions: list[dict[str, Any]]) -> dict[str, Any]:
    scope: dict[str, Any] = {}
    for item in resolutions:
        etype = item.get('type') or item.get('entity_type')
        value = item.get('value') or item.get('resolved_entity')
        display = item.get('display')
        if etype in ('camera', 'location') and value:
            scope['camera_id'] = str(value)
            if display:
                scope['location'] = display
                scope['display'] = display
                scope['display_name'] = display
        elif etype == 'violation_type' and value:
            scope['violation_type'] = value
        elif etype == 'vehicle_type' and value:
            scope['vehicle_type'] = value
        elif etype == 'vehicle_category' and value:
            scope['vehicle_category'] = value
        elif etype == 'plate_suffix' and value:
            scope['plate_suffix'] = value
    return normalize_entity_scope(scope)
__all__ = ['should_inherit', 'load_previous_plan', 'merge_scope', 'update_scope_from_result', 'entity_scope_from_resolutions', 'plan_snapshot']